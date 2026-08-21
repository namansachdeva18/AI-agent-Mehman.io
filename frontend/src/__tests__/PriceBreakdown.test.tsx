import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PriceBreakdown, type PriceBreakdownData } from '../components/chat/PriceBreakdown';

const mockPriceData: PriceBreakdownData = {
  room_name: 'Family Garden Suite',
  property_name: 'Azure Sands Resort',
  nights: 3,
  base_rate_per_night: 12500,
  room_subtotal: 37500,
  add_ons: [
    {
      id: 5,
      name: 'Breakfast Buffet',
      price: 800,
      pricing_type: 'PER_PERSON_PER_NIGHT',
      total: 12000,
    },
  ],
  total_price: 49500,
};

describe('PriceBreakdown Component', () => {
  it('renders line items and total formatted in INR ₹', () => {
    render(<PriceBreakdown data={mockPriceData} />);

    expect(screen.getByText(/Base Stay \(3 nights × ₹12,500\)/)).toBeInTheDocument();
    expect(screen.getByText('₹37,500')).toBeInTheDocument();
    expect(screen.getByText(/Breakfast Buffet/)).toBeInTheDocument();
    expect(screen.getByText('₹12,000')).toBeInTheDocument();
    expect(screen.getByText('₹49,500')).toBeInTheDocument();
  });

  it('triggers onProceedToHold when user clicks lock hold button', () => {
    const handleProceed = vi.fn();
    render(<PriceBreakdown data={mockPriceData} onProceedToHold={handleProceed} />);

    const holdBtn = screen.getByRole('button', { name: /Lock in 15-Minute Booking Hold/i });
    fireEvent.click(holdBtn);

    expect(handleProceed).toHaveBeenCalled();
  });
});
