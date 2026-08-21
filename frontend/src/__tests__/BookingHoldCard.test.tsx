import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BookingHoldCard, type BookingHoldData } from '../components/chat/BookingHoldCard';

describe('BookingHoldCard Component', () => {
  it('renders active booking hold details and temporary hold disclaimer', () => {
    // Expiry in 14 minutes
    const futureExpiry = new Date(Date.now() + 14 * 60 * 1000).toISOString();

    const mockHold: BookingHoldData = {
      hold_id: 'HOLD-AZURE-2026-9912',
      property_name: 'Azure Sands Resort',
      room_name: 'Family Garden Suite',
      guest_name: 'Naman Sachdeva',
      check_in: '2026-09-10',
      check_out: '2026-09-13',
      guests: 5,
      total_price: 49500,
      expires_at: futureExpiry,
    };

    render(<BookingHoldCard hold={mockHold} />);

    expect(screen.getByText('Azure Sands Resort')).toBeInTheDocument();
    expect(screen.getByText('Family Garden Suite')).toBeInTheDocument();
    expect(screen.getByText('Naman Sachdeva')).toBeInTheDocument();
    expect(screen.getByText('2026-09-10 → 2026-09-13')).toBeInTheDocument();
    expect(screen.getByText('5 Guests')).toBeInTheDocument();
    expect(screen.getByText('₹49,500')).toBeInTheDocument();
    expect(screen.getByText(/ACTIVE 15-MIN HOLD/)).toBeInTheDocument();
    expect(screen.getByText(/Physical room inventory is temporarily held/)).toBeInTheDocument();
  });

  it('renders expired state with refresh action button', () => {
    // Past expiry
    const pastExpiry = new Date(Date.now() - 60 * 1000).toISOString();

    const mockHold: BookingHoldData = {
      hold_id: 'HOLD-EXPIRED-1234',
      property_name: 'Azure Sands Resort',
      room_name: 'Family Garden Suite',
      guest_name: 'Naman Sachdeva',
      check_in: '2026-09-10',
      check_out: '2026-09-13',
      guests: 5,
      total_price: 49500,
      expires_at: pastExpiry,
    };

    const handleRefresh = vi.fn();
    render(<BookingHoldCard hold={mockHold} onRefreshAvailability={handleRefresh} />);

    expect(screen.getByText('HOLD EXPIRED')).toBeInTheDocument();
    expect(screen.getByText(/This booking hold has expired/)).toBeInTheDocument();

    const refreshBtn = screen.getByRole('button', { name: 'Check Availability Again' });
    fireEvent.click(refreshBtn);
    expect(handleRefresh).toHaveBeenCalled();
  });
});
