import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MessageBubble } from '../components/chat/MessageBubble';
import type { ChatMessage } from '../types';

describe('MessageBubble Component', () => {
  it('renders user message with distinct styling', () => {
    const msg: ChatMessage = {
      role: 'USER',
      content: 'I want a hotel in Goa for 4 people.',
      timestamp: new Date().toISOString(),
    };

    render(<MessageBubble message={msg} />);
    expect(screen.getByText('I want a hotel in Goa for 4 people.')).toBeInTheDocument();
    expect(screen.getByLabelText('User avatar')).toBeInTheDocument();
  });

  it('renders assistant message with bullet points and bold text', () => {
    const msg: ChatMessage = {
      role: 'ASSISTANT',
      content: 'Here are the top options:\n• **Grand Heritage Palace** in Jaipur\n• **Azure Sands Resort** in Goa',
      timestamp: new Date().toISOString(),
    };

    render(<MessageBubble message={msg} />);
    expect(screen.getByText('Grand Heritage Palace')).toBeInTheDocument();
    expect(screen.getByText('Azure Sands Resort')).toBeInTheDocument();
    expect(screen.getByLabelText('Assistant avatar')).toBeInTheDocument();
  });

  it('renders system error message correctly', () => {
    const msg: ChatMessage = {
      role: 'SYSTEM',
      content: '⚠ Connection to concierge service lost. Retrying...',
      timestamp: new Date().toISOString(),
    };

    render(<MessageBubble message={msg} />);
    expect(screen.getByText(/Connection to concierge service lost/)).toBeInTheDocument();
  });
});
