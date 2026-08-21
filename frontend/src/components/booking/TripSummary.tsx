import React from 'react';
import type { BookingState } from '../../types';

interface TripSummaryProps {
  bookingState: BookingState | null;
  onEditField: (promptText: string) => void;
}

export const TripSummary: React.FC<TripSummaryProps> = ({ bookingState, onEditField }) => {
  const destination = bookingState?.destination || 'Not specified';
  const checkIn = bookingState?.check_in;
  const checkOut = bookingState?.check_out;
  const dates = checkIn && checkOut ? `${checkIn} → ${checkOut}` : 'Not specified';
  const guests = bookingState?.guests ? `${bookingState.guests} ${bookingState.guests === 1 ? 'Guest' : 'Guests'}` : 'Not specified';
  const budget = bookingState?.budget_per_night ? `₹${bookingState.budget_per_night.toLocaleString('en-IN')}` : 'Not specified';
  const propertyName = bookingState?.selected_property_name || 'Not specified';
  const roomName = bookingState?.selected_room_name || 'Not specified';
  const amenities = bookingState?.preferred_amenities && bookingState.preferred_amenities.length > 0
    ? bookingState.preferred_amenities
    : null;

  return (
    <div className="trip-summary-card" aria-label="Trip overview parameters">
      <div className="trip-summary-header">
        <h4 className="panel-title">Your Trip Plan</h4>
        {bookingState?.destination && <span className="trip-badge">{bookingState.destination}</span>}
      </div>

      <div className="trip-chips-grid">
        {/* Destination */}
        <div className="trip-chip">
          <span className="chip-label">Destination</span>
          <div className="chip-value-row">
            <span className={`chip-value ${destination === 'Not specified' ? 'val-unspecified' : ''}`}>
              {destination}
            </span>
            <button
              type="button"
              className="chip-edit-btn"
              onClick={() => onEditField(destination !== 'Not specified' ? `Change destination from ${destination} to ` : 'I want to go to ')}
              title="Change destination"
              aria-label="Edit destination"
            >
              ✎
            </button>
          </div>
        </div>

        {/* Dates */}
        <div className="trip-chip">
          <span className="chip-label">Dates</span>
          <div className="chip-value-row">
            <span className={`chip-value ${dates === 'Not specified' ? 'val-unspecified' : ''}`}>
              {dates}
            </span>
            <button
              type="button"
              className="chip-edit-btn"
              onClick={() => onEditField('Change my stay dates to ')}
              title="Change stay dates"
              aria-label="Edit dates"
            >
              ✎
            </button>
          </div>
        </div>

        {/* Guests */}
        <div className="trip-chip">
          <span className="chip-label">Guests</span>
          <div className="chip-value-row">
            <span className={`chip-value ${guests === 'Not specified' ? 'val-unspecified' : ''}`}>
              {guests}
            </span>
            <button
              type="button"
              className="chip-edit-btn"
              onClick={() => onEditField('Update number of guests to ')}
              title="Change guests"
              aria-label="Edit guests"
            >
              ✎
            </button>
          </div>
        </div>

        {/* Budget */}
        <div className="trip-chip">
          <span className="chip-label">Budget / Night</span>
          <div className="chip-value-row">
            <span className={`chip-value ${budget === 'Not specified' ? 'val-unspecified' : ''}`}>
              {budget}
            </span>
            <button
              type="button"
              className="chip-edit-btn"
              onClick={() => onEditField('Change my nightly budget to ')}
              title="Change budget"
              aria-label="Edit budget"
            >
              ✎
            </button>
          </div>
        </div>

        {/* Selected Hotel */}
        <div className="trip-chip full-width">
          <span className="chip-label">Selected Hotel</span>
          <div className="chip-value-row">
            <span className={`chip-value ${propertyName === 'Not specified' ? 'val-unspecified' : 'selected-stay-name'}`}>
              {propertyName}
            </span>
            {propertyName !== 'Not specified' && (
              <button
                type="button"
                className="chip-edit-btn"
                onClick={() => onEditField('Show me other hotels in ' + (destination !== 'Not specified' ? destination : ''))}
                title="Change hotel"
                aria-label="Edit hotel"
              >
                ✎
              </button>
            )}
          </div>
        </div>

        {/* Selected Room */}
        <div className="trip-chip full-width">
          <span className="chip-label">Selected Room</span>
          <div className="chip-value-row">
            <span className={`chip-value ${roomName === 'Not specified' ? 'val-unspecified' : 'selected-stay-name'}`}>
              {roomName}
            </span>
            {roomName !== 'Not specified' && (
              <button
                type="button"
                className="chip-edit-btn"
                onClick={() => onEditField('Show other room types')}
                title="Change room"
                aria-label="Edit room"
              >
                ✎
              </button>
            )}
          </div>
        </div>

        {/* Preferences / Amenities */}
        {amenities && (
          <div className="trip-chip full-width">
            <span className="chip-label">Preferences & Amenities</span>
            <div className="amenity-tags">
              {amenities.map((am) => (
                <span key={am} className="tag-item">✓ {am}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

