import React, { useEffect, useRef } from 'react';
import type { ChatMessage } from '../../types';
import { MessageBubble } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';

interface MessageListProps {
  messages: ChatMessage[];
  isSending: boolean;
  onQuickAction?: (actionText: string) => void;
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  isSending,
  onQuickAction,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSending]);

  if (messages.length === 0) {
    return (
      <div className="empty-chat-state">
        <div className="empty-chat-hero">
          <div className="hero-badge">✦ Meet Mira — Luxury Hospitality Concierge</div>
          <h2 className="hero-title">Where would you like to stay?</h2>
          <p className="hero-subtitle">
            I am <strong>Mira</strong>, your AI hotel booking concierge for Mehman.io. Tell me your destination, dates, guest count, or preferences, and I'll find, compare, and hold the perfect room for you.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="message-list-container">
      {messages.map((msg, idx) => (
        <MessageBubble
          key={msg.id || `${msg.timestamp}-${idx}`}
          message={msg}
          onQuickAction={onQuickAction}
        />
      ))}
      {isSending && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
};
