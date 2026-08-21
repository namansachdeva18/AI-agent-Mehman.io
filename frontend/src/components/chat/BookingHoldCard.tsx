import React from 'react';
import { useCountdown } from '../../hooks/useCountdown';
import { Badge } from '../common/Badge';

export interface BookingHoldData {
  hold_id: string;
  property_name: string;
  room_name: string;
  guest_name?: string | null;
  check_in: string;
  check_out: string;
  guests?: number | null;
  total_price: number | null;
  expires_at: string;
  status?: string;
}

interface BookingHoldCardProps {
  hold: BookingHoldData;
  onRefreshAvailability?: () => void;
  onViewPolicies?: () => void;
}

export const BookingHoldCard: React.FC<BookingHoldCardProps> = ({
  hold,
  onRefreshAvailability,
  onViewPolicies,
}) => {
  const { formatted, isExpired } = useCountdown(hold.expires_at);

  return (
    <div className={`booking-hold-card ${isExpired ? 'hold-expired' : 'hold-active'}`}>
      <div className="hold-header">
        <div className="hold-status-indicator">
          <span className={`hold-pulse-dot ${isExpired ? 'dot-expired' : 'dot-active'}`} />
          <Badge variant={isExpired ? 'danger' : 'success'}>
            {isExpired ? 'HOLD EXPIRED' : 'ACTIVE 15-MIN HOLD'}
          </Badge>
        </div>

        {!isExpired && (
          <div className="hold-countdown-timer" aria-label="Hold expiration countdown">
            <span className="timer-icon">⏳</span>
            <span className="timer-value">{formatted}</span>
          </div>
        )}
      </div>

      <div className="hold-main-details">
        <h4 className="hold-property">{hold.property_name}</h4>
        <p className="hold-room">{hold.room_name}</p>

        <div className="hold-meta-grid">
          {hold.guest_name && (
            <div className="meta-item">
              <span className="meta-label">Guest</span>
              <span className="meta-val">{hold.guest_name}</span>
            </div>
          )}
          <div className="meta-item">
            <span className="meta-label">Dates</span>
            <span className="meta-val">{hold.check_in} → {hold.check_out}</span>
          </div>
          {hold.guests && (
            <div className="meta-item">
              <span className="meta-label">Guests</span>
              <span className="meta-val">{hold.guests} {hold.guests === 1 ? 'Guest' : 'Guests'}</span>
            </div>
          )}
          <div className="meta-item">
            <span className="meta-label">Hold ID</span>
            <span className="meta-val hold-id-code">{hold.hold_id.slice(0, 8)}...</span>
          </div>
        </div>

        {hold.total_price !== null && (
          <div className="hold-total-box">
            <span className="box-label">Locked Total Rate</span>
            <span className="box-amount">₹{hold.total_price.toLocaleString('en-IN')}</span>
          </div>
        )}
      </div>

      <div className="hold-footer-note">
        {isExpired ? (
          <p className="expired-message">
            ⚠️ This booking hold has expired and physical inventory was released.
          </p>
        ) : (
          <p className="active-message">
            🔒 Physical room inventory is temporarily held in SQLite for 15 minutes. Final payment is not yet processed.
          </p>
        )}
      </div>

      <div className="hold-actions-row">
        {isExpired ? (
          <button
            type="button"
            className="btn btn-secondary btn-sm btn-full"
            onClick={onRefreshAvailability}
          >
            Check Availability Again
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-secondary btn-sm btn-full"
            onClick={onViewPolicies}
          >
            View Cancellation & Stay Policies
          </button>
        )}
      </div>
    </div>
  );
};
