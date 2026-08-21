import React from 'react';
import type { ChatMessage, RecommendationCandidate } from '../../types';
import { BookingHoldCard, type BookingHoldData } from './BookingHoldCard';
import { HotelCard } from './HotelCard';
import { PriceBreakdown, type PriceBreakdownData } from './PriceBreakdown';
import { RoomCard, type RoomDetails } from './RoomCard';

interface MessageBubbleProps {
  message: ChatMessage;
  onQuickAction?: (actionText: string) => void;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  onQuickAction,
}) => {
  const isUser = message.role === 'USER' || message.role === 'guest';
  const isSystem = message.role === 'SYSTEM';

  const formatContent = (content: string) => {
    const paragraphs = content.split('\n');
    return paragraphs.map((line, idx) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return <div key={idx} className="bubble-spacer" />;
      }

      // Headings (###, ##, #)
      const headingMatch = trimmed.match(/^(#{1,3})\s+(.*)$/);
      if (headingMatch) {
        const level = headingMatch[1].length;
        const text = headingMatch[2];
        if (level === 1) return <h3 key={idx} className="bubble-heading-1">{renderFormattedText(text)}</h3>;
        if (level === 2) return <h4 key={idx} className="bubble-heading-2">{renderFormattedText(text)}</h4>;
        return <h5 key={idx} className="bubble-heading-3">{renderFormattedText(text)}</h5>;
      }

      if (trimmed.startsWith('•') || trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        const bulletText = trimmed.replace(/^[•\-*]\s+/, '');
        return (
          <div key={idx} className="bubble-bullet">
            <span className="bullet-dot">•</span>
            <span>{renderFormattedText(bulletText)}</span>
          </div>
        );
      }

      const numMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
      if (numMatch) {
        return (
          <div key={idx} className="bubble-numbered">
            <span className="bullet-num">{numMatch[1]}.</span>
            <span>{renderFormattedText(numMatch[2])}</span>
          </div>
        );
      }

      return (
        <p key={idx} className="bubble-paragraph">
          {renderFormattedText(trimmed)}
        </p>
      );
    });
  };

  const renderFormattedText = (text: string): React.ReactNode => {
    // Tokenize for bold (**...**), italics (*...* or _..._), and code (`...`)
    const parts = text.split(/(\*\*.*?\*\*|\*[^*]+?\*|`[^`]+?`)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
        return <strong key={i}>{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('*') && part.endsWith('*') && part.length >= 2) {
        return <em key={i}>{part.slice(1, -1)}</em>;
      }
      if (part.startsWith('`') && part.endsWith('`') && part.length >= 2) {
        return <code key={i} className="bubble-code">{part.slice(1, -1)}</code>;
      }
      return part;
    });
  };

  if (isSystem) {
    return (
      <div className="message-row system">
        <div className="system-notice">
          <span className="notice-icon">ℹ</span>
          <span className="notice-text">{message.content}</span>
        </div>
      </div>
    );
  }

  // Check for attached metadata cards
  const meta = message.metadata || {};
  const hotelRec = meta.hotel_recommendation as RecommendationCandidate | undefined;
  const roomDetails = meta.room_details as RoomDetails | undefined;
  const priceData = meta.price_breakdown as PriceBreakdownData | undefined;
  const holdData = meta.booking_hold as BookingHoldData | undefined;

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      {!isUser && (
        <div className="avatar assistant-avatar" aria-label="Assistant avatar">
          ✦
        </div>
      )}
      <div className={`bubble ${isUser ? 'user-bubble' : 'assistant-bubble'}`}>
        <div className="bubble-content">{formatContent(message.content)}</div>

        {/* Dynamic Card Attachments */}
        {hotelRec && onQuickAction && (
          <div className="bubble-card-attachment">
            <HotelCard
              hotel={hotelRec}
              onSelectRoom={(rId, rName) => onQuickAction(`Select room ${rId}: ${rName}`)}
            />
          </div>
        )}

        {roomDetails && onQuickAction && (
          <div className="bubble-card-attachment">
            <RoomCard
              room={roomDetails}
              onSelect={(rId, rName) => onQuickAction(`Select room ${rId}: ${rName}`)}
            />
          </div>
        )}

        {priceData && onQuickAction && (
          <div className="bubble-card-attachment">
            <PriceBreakdown
              data={priceData}
              onProceedToHold={() => onQuickAction(`Proceed to hold ${priceData.room_name}`)}
            />
          </div>
        )}

        {holdData && (
          <div className="bubble-card-attachment">
            <BookingHoldCard
              hold={holdData}
              onRefreshAvailability={() => onQuickAction?.('Check availability again')}
              onViewPolicies={() => onQuickAction?.('What are the cancellation policies?')}
            />
          </div>
        )}
      </div>
      {isUser && (
        <div className="avatar user-avatar" aria-label="User avatar">
          👤
        </div>
      )}
    </div>
  );
};

