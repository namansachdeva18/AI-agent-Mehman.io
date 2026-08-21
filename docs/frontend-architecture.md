# Frontend Architecture — Mehman.io AI Luxury Hotel Concierge

## 1. Overview
The Mehman.io frontend is a production-grade React 19 + TypeScript + Vite single-page application designed for conversational hotel booking and deterministic inventory locking.

The UI acts as a pure presentation and interaction layer:
- **Zero Frontend Calculations**: Pricing, room capacity, availability, and hold expirations are authoritative backend computations.
- **Dynamic Card Rendering**: Assistant responses are parsed and enriched with interactive cards (`HotelCard`, `RoomCard`, `PriceBreakdown`, `BookingHoldCard`, `AddOnSelector`).
- **Session Persistence**: Stored via `localStorage.mehman_session_id`, ensuring instant session recovery upon browser refresh.

---

## 2. Component Hierarchy

```
App
├── Header (Brand, Connectivity Badge, Mobile Plan Drawer Toggle, New Stay Action)
├── Main (app-layout)
│   ├── ChatPanel (section.chat-panel)
│   │   ├── MessageList
│   │   │   ├── MessageBubble (User / Assistant / System / Rich Cards)
│   │   │   │   ├── HotelCard (Recommendations, Ratings, Verified Amenities)
│   │   │   │   ├── RoomCard (Capacity, SqFt, Bed Type, Direct Select)
│   │   │   │   ├── PriceBreakdown (Line Items, Add-ons, Formatted INR Total)
│   │   │   │   └── BookingHoldCard (15-min Countdown, Locked Total, Hold ID)
│   │   │   └── TypingIndicator (Contextual Human-Readable Loading States)
│   │   ├── SuggestedPrompts (Missing-Field Guided Prompts)
│   │   └── ChatInput (Textarea, Keyboard Shortcuts, Send Action)
│   └── BookingPanel (aside.booking-panel & Mobile Sheet)
│       ├── HoldStatusCard (Visual 15-Minute Countdown & Action Buttons)
│       ├── TripSummary (Destination, Dates, Guests, Budget, Hotel, Room)
│       └── ConciergeGuaranteesCard (Direct Rates, Real-Time Inventory, Accuracy)
└── Modal (Hold Abandonment Confirmation)
```

---

## 3. State Management & Hooks

### `useChat` (`src/hooks/useChat.ts`)
- Manages conversation lifecycle, message history, active booking state, and optimistic locking reconciliation.
- Provides `sendMessage`, `startNewConversation`, `reconcileSession`, `activeHold`.

### `useCountdown` (`src/hooks/useCountdown.ts`)
- Calculates remaining seconds and formatted string (`MM:SS`) from backend ISO `expires_at` timestamp.
- Automatically transitions UI to expired state when countdown completes without polling backend.

---

## 4. API Communication (`src/services/api.ts`)
- `sendMessage(message, sessionId)`: Dispatches chat turn to FastAPI `/api/chat`.
- `createConversation()`: Initializes fresh persistent conversation session.
- `getConversation(sessionId)`: Restores full history and booking state on page load.
- `healthCheck()`: Queries `/health` to display live server status.

---

## 5. Responsive Design & Accessibility

### Breakpoints
- **Desktop (1440px, 1280px, 1024px)**: Dual-pane layout (Chat on left, Booking State Sidebar on right).
- **Tablet & Mobile (768px, 430px, 390px, 375px)**:
  - Chat occupies primary full-width viewport.
  - Booking State converts to an accessible slide-up bottom drawer toggled via `Header` button.
  - Touch-friendly tap targets ($\ge 44\text{px}$) and thumb-friendly quick chips.

### Accessibility Standards
- Semantic HTML tags (`<header>`, `<main>`, `<section>`, `<aside>`, `<article>`).
- ARIA live status attributes (`role="status"`, `aria-live="polite"`, `aria-label`).
- Accessible form controls with visible focus rings and keyboard navigation (`Enter` to submit, `Shift+Enter` for newlines).

---

## 6. Testing Suite
- **Unit & Integration Suite**: Vitest + React Testing Library (`src/__tests__/`).
- **Test Coverage**:
  - `ChatMessage.test.tsx`: Markdown parsing, avatars, system error rows.
  - `MessageInput.test.tsx`: Textarea expansion, enter keys, disabled gates.
  - `HotelCard.test.tsx`: Ratings, amenities, sold-out states, room selection.
  - `RoomCard.test.tsx`: Specs, pricing, availability badges, selection.
  - `PriceBreakdown.test.tsx`: Subtotals, add-ons, ₹ formatting, hold action.
  - `BookingHoldCard.test.tsx`: Active timer, disclaimer, expired state.
  - `BookingPanel.test.tsx`: "Not specified" fallbacks, parameter edits.
  - `SessionPersistence.test.tsx`: LocalStorage session lifecycle.
