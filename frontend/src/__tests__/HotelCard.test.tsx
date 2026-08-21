import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HotelCard } from '../components/chat/HotelCard';
import type { RecommendationCandidate } from '../types';

const mockHotel: RecommendationCandidate = {
  property_id: 2,
  property_name: 'Azure Sands Resort',
  city: 'Goa',
  star_rating: 5,
  room_id: 5,
  room_name: 'Family Garden Suite',
  room_size_sqft: 650,
  bed_type: '2 Queen Beds',
  nightly_price: 12500,
  total_price: 37500,
  max_guests: 5,
  available: true,
  matched_amenities: ['Pool', 'Free WiFi', 'Beach Access', 'Spa'],
  unmatched_preferences: [],
  match_type: 'EXACT_MATCH',
  score_breakdown: {
    preference_match: 1,
    value_score: 0.9,
    quality_score: 1,
    capacity_fit: 1,
    amenity_match: 1,
    final_score: 0.98,
  },
  recommendation_reason: 'Top match for family vacations in Goa with direct beachfront access.',
};

describe('HotelCard Component', () => {
  it('renders hotel details, rating, and verified amenities', () => {
    const handleSelect = vi.fn();
    render(<HotelCard hotel={mockHotel} onSelectRoom={handleSelect} />);

    expect(screen.getByText('Azure Sands Resort')).toBeInTheDocument();
    expect(screen.getByText('📍 Goa')).toBeInTheDocument();
    expect(screen.getByText('Family Garden Suite')).toBeInTheDocument();
    expect(screen.getByText('₹12,500')).toBeInTheDocument();
    expect(screen.getByText('Available')).toBeInTheDocument();
    expect(screen.getByText('✓ Pool')).toBeInTheDocument();
  });

  it('triggers onSelectRoom with valid database IDs on button click', () => {
    const handleSelect = vi.fn();
    render(<HotelCard hotel={mockHotel} onSelectRoom={handleSelect} />);

    const selectBtn = screen.getByRole('button', { name: /Select Family Garden Suite/i });
    fireEvent.click(selectBtn);

    expect(handleSelect).toHaveBeenCalledWith(5, 'Family Garden Suite', 'Azure Sands Resort');
  });

  it('disables selection button when room is sold out', () => {
    const soldOutHotel = { ...mockHotel, available: false };
    const handleSelect = vi.fn();
    render(<HotelCard hotel={soldOutHotel} onSelectRoom={handleSelect} />);

    const selectBtn = screen.getByRole('button', { name: /Select Family Garden Suite/i });
    expect(selectBtn).toBeDisabled();
    expect(screen.getByText('Sold Out')).toBeInTheDocument();
  });
});
