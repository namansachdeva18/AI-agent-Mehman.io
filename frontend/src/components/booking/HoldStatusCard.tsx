import React from 'react';
import { useCountdown } from '../../hooks/useCountdown';
import type { BookingState } from '../../types';

interface HoldStatusCardProps {
  bookingState: BookingState;
  onQuickAction: (text: string) => void;
  onExpire?: () => void;
}

export const HoldStatusCard: React.FC<HoldStatusCardProps> = ({
  bookingState,
  onQuickAction,
  onExpire,
}) => {
  const { formatted, isExpired } = useCountdown(bookingState.hold_expires_at, onExpire);

  if (!bookingState.hold_id) return null;

  return (
    <div className={`hold-card ${isExpired ? 'expired' : 'active'}`}>
      <div className="hold-card-header">
        <div className="hold-badge">
          <span className="hold-badge-dot" />
          <span>{isExpired ? 'HOLD EXPIRED' : 'ACTIVE ROOM HOLD'}</span>
        </div>
        {!isExpired && (
          <div className="hold-timer">
            <span className="timer-icon">⏳</span>
            <span className="timer-digits">{formatted}</span>
          </div>
        )}
      </div>

      <div className="hold-details">
        <div className="hold-hotel-name">
          {bookingState.selected_property_name || 'Selected Property'}
        </div>
        <div className="hold-room-name">
          {bookingState.selected_room_name || 'Selected Room'}
        </div>
        {bookingState.hold_total_price !== null && (
          <div className="hold-price">
            Total Locked Rate: <strong>₹{bookingState.hold_total_price.toLocaleString('en-IN')}</strong>
          </div>
        )}
      </div>

      <div className="hold-disclaimer">
        ⚠️ This room is locked for 15 minutes to guarantee availability and pricing.
      </div>

      <div className="hold-actions">
        {isExpired ? (
          <button
            type="button"
            className="btn btn-secondary btn-sm btn-full"
            onClick={() => onQuickAction('Check availability again')}
          >
            Refresh Availability
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-secondary btn-sm btn-full"
            onClick={() => onQuickAction('What cancellation policies apply to this hold?')}
          >
            View Policies
          </button>
        )}
      </div>
    </div>
  );
};
