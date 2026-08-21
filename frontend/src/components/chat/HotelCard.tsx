import React from 'react';
import type { RecommendationCandidate } from '../../types';
import { Badge } from '../common/Badge';

interface HotelCardProps {
  hotel: RecommendationCandidate;
  onSelectRoom: (roomId: number, roomName: string, propertyName: string) => void;
  isSelected?: boolean;
}

export const HotelCard: React.FC<HotelCardProps> = ({
  hotel,
  onSelectRoom,
  isSelected = false,
}) => {
  const stars = Array.from({ length: hotel.star_rating || 4 }, (_, i) => i + 1);

  return (
    <article className={`hotel-card ${isSelected ? 'hotel-card-selected' : ''}`}>
      <div className="hotel-card-media" aria-hidden="true">
        <div className="hotel-card-placeholder">
          <span className="placeholder-icon">🏨</span>
          <span className="placeholder-city">{hotel.city}</span>
        </div>
        <div className="hotel-card-rating">
          {stars.map((s) => (
            <span key={s} className="star-icon">★</span>
          ))}
        </div>
      </div>

      <div className="hotel-card-body">
        <div className="hotel-header-row">
          <div>
            <h4 className="hotel-name">{hotel.property_name}</h4>
            <p className="hotel-location">📍 {hotel.city}</p>
          </div>
          <div className="hotel-price-badge">
            <span className="price-label">from</span>
            <span className="price-amount">₹{hotel.nightly_price.toLocaleString('en-IN')}</span>
            <span className="price-unit">/ night</span>
          </div>
        </div>

        {hotel.recommendation_reason && (
          <div className="hotel-reason">
            <span className="reason-icon">✦</span>
            <p className="reason-text">{hotel.recommendation_reason}</p>
          </div>
        )}

        <div className="hotel-room-preview">
          <div className="preview-header">
            <span className="room-title">{hotel.room_name}</span>
            <Badge variant={hotel.available ? 'success' : 'danger'}>
              {hotel.available ? 'Available' : 'Sold Out'}
            </Badge>
          </div>
          <div className="room-specs">
            <span>👥 Up to {hotel.max_guests} {hotel.max_guests === 1 ? 'Guest' : 'Guests'}</span>
            {hotel.room_size_sqft > 0 && <span>📐 {hotel.room_size_sqft} sq ft</span>}
            {hotel.bed_type && <span>🛏 {hotel.bed_type}</span>}
          </div>
        </div>

        {hotel.matched_amenities && hotel.matched_amenities.length > 0 && (
          <div className="hotel-amenities">
            {hotel.matched_amenities.slice(0, 4).map((am) => (
              <span key={am} className="amenity-chip">✓ {am}</span>
            ))}
          </div>
        )}

        <div className="hotel-card-footer">
          <button
            type="button"
            className={`btn btn-sm ${isSelected ? 'btn-secondary' : 'btn-primary'} btn-full`}
            onClick={() => onSelectRoom(hotel.room_id, hotel.room_name, hotel.property_name)}
            disabled={!hotel.available}
            aria-label={`Select ${hotel.room_name} at ${hotel.property_name}`}
          >
            {isSelected ? '✓ Room Selected' : 'Select This Room'}
          </button>
        </div>
      </div>
    </article>
  );
};
