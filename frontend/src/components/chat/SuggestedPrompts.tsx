import React from 'react';
import type { BookingState } from '../../types';

interface SuggestedPromptsProps {
  bookingState: BookingState | null;
  onSelectPrompt: (prompt: string) => void;
  disabled?: boolean;
}

export const SuggestedPrompts: React.FC<SuggestedPromptsProps> = ({
  bookingState,
  onSelectPrompt,
  disabled = false,
}) => {
  let suggestions: string[] = [];

  if (!bookingState || !bookingState.destination) {
    suggestions = [
      'Find a family hotel in Goa',
      'Luxury palace stay in Jaipur',
      'Mountain lodge in Manali for 2',
      'Beachfront resort for 4 people',
    ];
  } else if (!bookingState.check_in || !bookingState.check_out) {
    suggestions = [
      'September 10 to 13 for 2 adults',
      'October 5 to 8 for 4 people',
      'December 20 to 25 with mountain view',
    ];
  } else if (!bookingState.selected_room_id) {
    suggestions = [
      'Show me the cheapest option',
      'Which room has the best luxury amenities?',
      'I want the second recommendation',
    ];
  } else if (!bookingState.hold_id) {
    suggestions = [
      'Does it include breakfast or airport transfer?',
      'Add breakfast for all guests',
      'Place a 15-minute booking hold',
    ];
  } else {
    suggestions = [
      'What policies apply to this hold?',
      'Check another date range',
      'Find activities in this area',
    ];
  }

  return (
    <div className="suggested-prompts-container">
      <span className="prompts-label">Quick suggestions:</span>
      <div className="prompts-list">
        {suggestions.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="prompt-chip"
            onClick={() => onSelectPrompt(prompt)}
            disabled={disabled}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
};
