import React, { useEffect, useState } from 'react';

const STATUS_MESSAGES = [
  'Understanding your request...',
  'Searching available hotels...',
  'Checking room availability...',
  'Calculating your stay...',
  'Preparing your booking details...',
];

interface TypingIndicatorProps {
  customStatus?: string;
}

export const TypingIndicator: React.FC<TypingIndicatorProps> = ({ customStatus }) => {
  const [msgIndex, setMsgIndex] = useState(0);

  useEffect(() => {
    if (customStatus) return;
    const timer = setInterval(() => {
      setMsgIndex((prev) => (prev + 1) % STATUS_MESSAGES.length);
    }, 2200);
    return () => clearInterval(timer);
  }, [customStatus]);

  const displayMessage = customStatus || STATUS_MESSAGES[msgIndex];

  return (
    <div className="message-row assistant" role="status" aria-live="polite">
      <div className="avatar assistant-avatar" aria-label="Assistant avatar">
        ✦
      </div>
      <div className="bubble typing-bubble">
        <div className="typing-dots" aria-hidden="true">
          <span className="dot" />
          <span className="dot" />
          <span className="dot" />
        </div>
        <span className="typing-label">{displayMessage}</span>
      </div>
    </div>
  );
};

