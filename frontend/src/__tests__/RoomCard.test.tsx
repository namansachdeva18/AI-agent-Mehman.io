import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RoomCard, type RoomDetails } from '../components/chat/RoomCard';

const mockRoom: RoomDetails = {
  room_id: 4,
  room_name: 'Superior Ocean View Room',
  property_name: 'Azure Sands Resort',
  max_guests: 2,
  room_size_sqft: 450,
  bed_type: '1 King Bed',
  nightly_price: 8500,
  total_price: 25500,
  available: true,
  amenities: ['Ocean View', 'Balcony', 'Breakfast Included'],
};

describe('RoomCard Component', () => {
  it('renders room specifications and nightly price', () => {
    const handleSelect = vi.fn();
    render(<RoomCard room={mockRoom} onSelect={handleSelect} />);

    expect(screen.getByText('Superior Ocean View Room')).toBeInTheDocument();
    expect(screen.getByText('₹8,500')).toBeInTheDocument();
    expect(screen.getByText(/450 sq ft/)).toBeInTheDocument();
    expect(screen.getByText(/1 King Bed/)).toBeInTheDocument();
    expect(screen.getByText('Available')).toBeInTheDocument();
  });

  it('triggers onSelect when user clicks Choose This Room', () => {
    const handleSelect = vi.fn();
    render(<RoomCard room={mockRoom} onSelect={handleSelect} />);

    const chooseBtn = screen.getByRole('button', { name: /Select Superior Ocean View Room/i });
    fireEvent.click(chooseBtn);

    expect(handleSelect).toHaveBeenCalledWith(4, 'Superior Ocean View Room');
  });
});
