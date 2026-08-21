import React from 'react';
import { Badge } from '../common/Badge';

export interface RoomDetails {
  room_id: number;
  room_name: string;
  property_name?: string;
  max_guests: number;
  room_size_sqft: number;
  bed_type: string;
  nightly_price: number;
  total_price?: number | null;
  available?: boolean;
  amenities?: string[];
  description?: string;
}

interface RoomCardProps {
  room: RoomDetails;
  onSelect: (roomId: number, roomName: string) => void;
  isSelected?: boolean;
}

export const RoomCard: React.FC<RoomCardProps> = ({
  room,
  onSelect,
  isSelected = false,
}) => {
  const isAvailable = room.available !== false;

  return (
    <div className={`room-card ${isSelected ? 'room-card-selected' : ''}`}>
      <div className="room-card-header">
        <div className="room-title-area">
          {room.property_name && <span className="room-property-subtitle">{room.property_name}</span>}
          <h4 className="room-name">{room.room_name}</h4>
        </div>
        <div className="room-price-tag">
          <span className="room-rate">₹{room.nightly_price.toLocaleString('en-IN')}</span>
          <span className="room-unit">/ night</span>
        </div>
      </div>

      <div className="room-spec-grid">
        <div className="spec-item">
          <span className="spec-icon">👥</span>
          <span className="spec-val">Max {room.max_guests} Guests</span>
        </div>
        {room.room_size_sqft > 0 && (
          <div className="spec-item">
            <span className="spec-icon">📐</span>
            <span className="spec-val">{room.room_size_sqft} sq ft</span>
          </div>
        )}
        {room.bed_type && (
          <div className="spec-item">
            <span className="spec-icon">🛏</span>
            <span className="spec-val">{room.bed_type}</span>
          </div>
        )}
        <div className="spec-item">
          <Badge variant={isAvailable ? 'success' : 'danger'}>
            {isAvailable ? 'Available' : 'Sold Out'}
          </Badge>
        </div>
      </div>

      {room.amenities && room.amenities.length > 0 && (
        <div className="room-amenities-wrap">
          {room.amenities.map((am) => (
            <span key={am} className="amenity-chip">✓ {am}</span>
          ))}
        </div>
      )}

      {room.total_price !== undefined && room.total_price !== null && (
        <div className="room-total-calculated">
          <span>Estimated Stay Total:</span>
          <strong>₹{room.total_price.toLocaleString('en-IN')}</strong>
        </div>
      )}

      <div className="room-card-actions">
        <button
          type="button"
          className={`btn btn-sm ${isSelected ? 'btn-secondary' : 'btn-primary'} btn-full`}
          onClick={() => onSelect(room.room_id, room.room_name)}
          disabled={!isAvailable}
          aria-label={`Select ${room.room_name}`}
        >
          {isSelected ? '✓ Selected' : 'Choose This Room'}
        </button>
      </div>
    </div>
  );
};
