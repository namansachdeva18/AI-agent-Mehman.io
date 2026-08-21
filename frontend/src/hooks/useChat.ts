import { useCallback, useEffect, useState } from 'react';
import {
  ApiError,
  clearStoredSessionId,
  createConversation,
  getConversation,
  getStoredSessionId,
  sendMessage as apiSendMessage,
} from '../services/api';
import type {
  BookingState,
  ChatMessage,
  ConversationState,
  ToolExecutionEvent,
} from '../types';

export interface ExecutionTraceData {
  stateUpdates?: Record<string, unknown>;
  toolEvents: ToolExecutionEvent[];
  nextAction?: string;
  error?: string | null;
  timestamp: string;
}

export interface UseChatResult {
  sessionId: string | null;
  messages: ChatMessage[];
  bookingState: BookingState | null;
  isSending: boolean;
  isInitializing: boolean;
  error: string | null;
  latestTrace: ExecutionTraceData | null;
  activeHold: {
    holdId: string;
    expiresAt: string;
    totalPrice: number | null;
  } | null;
  sendMessage: (text: string) => Promise<void>;
  startNewConversation: () => Promise<void>;
  clearError: () => void;
  reconcileSession: () => Promise<void>;
}

export function useChat(): UseChatResult {
  const [sessionId, setSessionId] = useState<string | null>(getStoredSessionId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [bookingState, setBookingState] = useState<BookingState | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [latestTrace, setLatestTrace] = useState<ExecutionTraceData | null>(null);

  // Reconcile session state from backend
  const reconcileSession = useCallback(async () => {
    const storedId = getStoredSessionId();
    if (!storedId) {
      setIsInitializing(false);
      return;
    }

    try {
      const conv: ConversationState = await getConversation(storedId);
      setSessionId(conv.session_id);
      setMessages(conv.messages || []);
      setBookingState(conv.booking || null);
      setError(null);
    } catch {
      // Stored session not found or invalid -> clear and start fresh
      clearStoredSessionId();
      setSessionId(null);
      setMessages([]);
      setBookingState(null);
    } finally {
      setIsInitializing(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    reconcileSession();
  }, [reconcileSession]);

  const handleSendMessage = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isSending) return;

    setError(null);
    const nowIso = new Date().toISOString();
    const tempUserMsg: ChatMessage = {
      role: 'USER',
      content: trimmed,
      timestamp: nowIso,
    };

    setMessages((prev) => [...prev, tempUserMsg]);
    setIsSending(true);

    try {
      const res = await apiSendMessage(trimmed, sessionId || undefined);
      setSessionId(res.conversation_id || res.session_id);
      setBookingState(res.booking_state);

      // Record latest execution trace
      setLatestTrace({
        toolEvents: res.tool_events || [],
        nextAction: res.next_action,
        error: null,
        timestamp: new Date().toISOString(),
      });

      const assistantMsg: ChatMessage = {
        role: 'ASSISTANT',
        content: res.message || res.reply,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      let errMsg = 'Failed to connect to assistant. Please try again.';
      if (err instanceof ApiError) {
        errMsg = err.message;
      } else if (err instanceof Error) {
        errMsg = err.message;
      }
      setError(errMsg);

      setLatestTrace({
        toolEvents: [],
        nextAction: 'HANDLE_ERROR',
        error: errMsg,
        timestamp: new Date().toISOString(),
      });

      const errorNotice: ChatMessage = {
        role: 'SYSTEM',
        content: `⚠ ${errMsg}`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorNotice]);
    } finally {
      setIsSending(false);
    }
  }, [isSending, sessionId]);

  const startNewConversation = useCallback(async () => {
    try {
      setIsInitializing(true);
      setError(null);
      setLatestTrace(null);
      clearStoredSessionId();
      const newConv = await createConversation();
      setSessionId(newConv.session_id);
      setMessages([]);
      setBookingState(newConv.booking);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Could not create new session';
      setError(msg);
    } finally {
      setIsInitializing(false);
    }
  }, []);

  const activeHold = bookingState?.hold_id && bookingState?.hold_expires_at ? {
    holdId: bookingState.hold_id,
    expiresAt: bookingState.hold_expires_at,
    totalPrice: bookingState.hold_total_price,
  } : null;

  return {
    sessionId,
    messages,
    bookingState,
    isSending,
    isInitializing,
    error,
    latestTrace,
    activeHold,
    sendMessage: handleSendMessage,
    startNewConversation,
    clearError: () => setError(null),
    reconcileSession,
  };
}
