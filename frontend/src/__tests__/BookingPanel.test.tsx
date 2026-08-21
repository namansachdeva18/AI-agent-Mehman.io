import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BookingPanel } from '../components/booking/BookingPanel';
import type { BookingState } from '../types';

describe('BookingPanel Component', () => {
  it('displays "Not specified" for missing trip parameters', () => {
    const emptyState: BookingState = {
      destination: null,
      check_in: null,
      check_out: null,
      guests: null,
      adults: null,
      children: null,
      budget_per_night: null,
      preferred_amenities: [],
      room_preferences: [],
      special_requirements: [],
      selected_property_id: null,
      selected_property_name: null,
      selected_room_id: null,
      selected_room_name: null,
      selected_add_on_ids: [],
      hold_id: null,
      hold_total_price: null,
      hold_expires_at: null,
    };

    const handleAction = vi.fn();
    render(<BookingPanel bookingState={emptyState} onQuickAction={handleAction} />);

    const unspecifiedElements = screen.getAllByText('Not specified');
    expect(unspecifiedElements.length).toBeGreaterThanOrEqual(4);
  });

  it('displays populated parameters and triggers edit prompt', () => {
    const populatedState: BookingState = {
      destination: 'Goa',
      check_in: '2026-09-10',
      check_out: '2026-09-13',
      guests: 4,
      adults: 4,
      children: 0,
      budget_per_night: 15000,
      preferred_amenities: ['Beach Access'],
      room_preferences: [],
      special_requirements: [],
      selected_property_id: 2,
      selected_property_name: 'Azure Sands Resort',
      selected_room_id: 5,
      selected_room_name: 'Family Garden Suite',
      selected_add_on_ids: [],
      hold_id: null,
      hold_total_price: null,
      hold_expires_at: null,
    };

    const handleAction = vi.fn();
    render(<BookingPanel bookingState={populatedState} onQuickAction={handleAction} />);

    expect(screen.getAllByText('Goa').length).toBeGreaterThan(0);
    expect(screen.getAllByText('2026-09-10 → 2026-09-13').length).toBeGreaterThan(0);
    expect(screen.getAllByText('4 Guests').length).toBeGreaterThan(0);
    expect(screen.getAllByText('₹15,000/night').length + screen.getAllByText('₹15,000').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Azure Sands Resort').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Family Garden Suite').length).toBeGreaterThan(0);

    const editDestinationBtn = screen.getByLabelText('Edit destination');
    fireEvent.click(editDestinationBtn);
    expect(handleAction).toHaveBeenCalledWith('Change destination from Goa to ');
  });
});
