import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ChatInput } from '../components/chat/ChatInput';

describe('ChatInput Component', () => {
  it('renders textarea with placeholder and submit button', () => {
    const handleSend = vi.fn();
    render(<ChatInput onSend={handleSend} />);

    const textarea = screen.getByLabelText('Message to Mehman AI Concierge');
    expect(textarea).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send message' })).toBeInTheDocument();
  });

  it('triggers onSend on button click when text is typed', () => {
    const handleSend = vi.fn();
    render(<ChatInput onSend={handleSend} />);

    const textarea = screen.getByLabelText('Message to Mehman AI Concierge');
    fireEvent.change(textarea, { target: { value: 'Book Goa hotel' } });

    const sendBtn = screen.getByRole('button', { name: 'Send message' });
    fireEvent.click(sendBtn);

    expect(handleSend).toHaveBeenCalledWith('Book Goa hotel');
    expect(textarea).toHaveValue('');
  });

  it('triggers onSend on Enter keypress without Shift', () => {
    const handleSend = vi.fn();
    render(<ChatInput onSend={handleSend} />);

    const textarea = screen.getByLabelText('Message to Mehman AI Concierge');
    fireEvent.change(textarea, { target: { value: 'Reserve room' } });
    fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter', shiftKey: false });

    expect(handleSend).toHaveBeenCalledWith('Reserve room');
  });

  it('does not trigger onSend when disabled or empty', () => {
    const handleSend = vi.fn();
    render(<ChatInput onSend={handleSend} disabled={true} />);

    const textarea = screen.getByLabelText('Message to Mehman AI Concierge');
    fireEvent.change(textarea, { target: { value: 'Hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' });

    expect(handleSend).not.toHaveBeenCalled();
  });
});
