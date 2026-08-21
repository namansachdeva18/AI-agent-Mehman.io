import React from 'react';
import type { BookingState } from '../../types';
import type { ExecutionTraceData } from '../../hooks/useChat';
import { ExecutionTrace } from './ExecutionTrace';
import { HoldStatusCard } from './HoldStatusCard';
import { TripSummary } from './TripSummary';

interface BookingPanelProps {
  bookingState: BookingState | null;
  trace?: ExecutionTraceData | null;
  isSending?: boolean;
  onQuickAction: (actionText: string) => void;
  onExpire?: () => void;
  isOpenOnMobile?: boolean;
  onCloseMobile?: () => void;
}

export const BookingPanel: React.FC<BookingPanelProps> = ({
  bookingState,
  trace = null,
  isSending = false,
  onQuickAction,
  onExpire,
  isOpenOnMobile = false,
  onCloseMobile,
}) => {
  return (
    <aside className={`booking-panel ${isOpenOnMobile ? 'mobile-open' : ''}`} aria-label="Trip overview and booking hold sidebar">
      {onCloseMobile && (
        <div className="mobile-panel-header">
          <span className="mobile-panel-title">Trip Plan & Status</span>
          <button
            type="button"
            className="mobile-close-btn"
            onClick={onCloseMobile}
            aria-label="Close trip panel"
          >
            ✕
          </button>
        </div>
      )}

      {bookingState?.hold_id && (
        <HoldStatusCard
          bookingState={bookingState}
          onQuickAction={onQuickAction}
          onExpire={onExpire}
        />
      )}

      <ExecutionTrace
        trace={trace}
        bookingState={bookingState}
        isSending={isSending}
      />

      <TripSummary
        bookingState={bookingState}
        onEditField={onQuickAction}
      />

      <div className="concierge-guarantees-card">
        <h5 className="guarantees-title">✦ Mehman Direct Guarantees</h5>
        <ul className="guarantees-list">
          <li><strong>Direct Rates:</strong> 100% database-verified pricing with no hidden markups.</li>
          <li><strong>Real-time Availability:</strong> Room holds lock physical inventory instantly for 15 minutes.</li>
          <li><strong>Deterministic Accuracy:</strong> All quotes and amenities come strictly from authoritative records.</li>
        </ul>
      </div>
    </aside>
  );
};

