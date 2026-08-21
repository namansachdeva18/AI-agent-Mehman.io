/**
 * API service layer for communicating with the FastAPI backend.
 * Provides typed methods for chat, persistent session management,
 * and deterministic hotel exploration.
 */

import type {
  ChatApiResponse,
  ChatMessage,
  ConversationState,
  HealthResponse,
  MessageRole,
  StateResponse,
} from '../types';

const API_BASE = (import.meta.env.VITE_API_URL || 'https://ai-agent-mehman-io.onrender.com').replace(/\/+$/, '');
const SESSION_STORAGE_KEY = 'mehman_session_id';

export interface ApiErrorDetail {
  code: string;
  message: string;
  retryable?: boolean;
  request_id?: string;
}

export class ApiError extends Error {
  code: string;
  retryable: boolean;
  requestId?: string;
  status: number;

  constructor(status: number, detail: ApiErrorDetail) {
    super(detail.message || `Request failed with status ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = detail.code || 'UNKNOWN_ERROR';
    this.retryable = Boolean(detail.retryable);
    this.requestId = detail.request_id;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const errDetail: ApiErrorDetail = errorBody.error || {
      code: 'HTTP_ERROR',
      message: errorBody.message || `HTTP ${response.status}: ${response.statusText}`,
      retryable: response.status >= 500,
    };
    throw new ApiError(response.status, errDetail);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

/** Check backend health and Gemini configuration status. */
export async function healthCheck(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

/** Get or create stored conversation session ID in browser localStorage. */
export function getStoredSessionId(): string | null {
  return localStorage.getItem(SESSION_STORAGE_KEY);
}

export function setStoredSessionId(sessionId: string): void {
  localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
}

export function clearStoredSessionId(): void {
  localStorage.removeItem(SESSION_STORAGE_KEY);
}

/** Create a new persistent conversation. */
export async function createConversation(conversationId?: string): Promise<ConversationState> {
  const conv = await request<ConversationState>('/api/conversations', {
    method: 'POST',
    body: JSON.stringify(conversationId ? { conversation_id: conversationId } : {}),
  });
  setStoredSessionId(conv.session_id);
  return conv;
}

/** Retrieve conversation session by ID. */
export async function getConversation(conversationId: string): Promise<ConversationState> {
  return request<ConversationState>(`/api/conversations/${conversationId}`);
}

/** Append a message to a conversation. */
export async function appendMessage(
  conversationId: string,
  content: string,
  role: MessageRole = 'USER',
  metadata: Record<string, unknown> = {}
): Promise<ChatMessage> {
  return request<ChatMessage>(`/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ role, content, metadata }),
  });
}

/** Get message history for a conversation. */
export async function getMessages(conversationId: string): Promise<ChatMessage[]> {
  return request<ChatMessage[]>(`/api/conversations/${conversationId}/messages`);
}

/** Get current booking state and missing fields. */
export async function getBookingState(conversationId: string): Promise<StateResponse> {
  return request<StateResponse>(`/api/conversations/${conversationId}/state`);
}

/** Close or abandon an existing conversation. */
export async function closeConversation(
  conversationId: string,
  status: 'COMPLETED' | 'ABANDONED' = 'COMPLETED'
): Promise<void> {
  await request<void>(`/api/conversations/${conversationId}/close`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  });
}

/** Send a chat message to the agent orchestrator. */
export async function sendMessage(
  message: string,
  sessionId?: string
): Promise<ChatApiResponse> {
  const currentSession = sessionId || getStoredSessionId() || undefined;
  const payload = {
    message,
    session_id: currentSession,
    conversation_id: currentSession,
  };

  const res = await request<ChatApiResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  const resolvedSessionId = res.conversation_id || res.session_id;
  if (resolvedSessionId) {
    setStoredSessionId(resolvedSessionId);
  }
  return res;
}
