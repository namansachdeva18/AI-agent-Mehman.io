# Phase 7 Frontend Architecture & Product Guide

## 1. Overview
Phase 7 establishes a production-grade conversational hotel booking interface for **Mehman.io**. It moves away from developer prototypes and delivers a warm luxury aesthetic inspired by high-end hospitality services.

---

## 2. Component Architecture
```
frontend/src/
├── App.tsx                     # Top-level orchestrator & modal coordinator
├── components/
│   ├── layout/
│   │   ├── Header.tsx          # Brand header with connection status & New Stay CTA
│   │   └── Modal.tsx           # Accessible confirmation dialogs
│   ├── chat/
│   │   ├── MessageList.tsx     # Chronological message feed & welcome hero state
│   │   ├── MessageBubble.tsx   # Paragraph, bullet, and bold message formatting
│   │   ├── TypingIndicator.tsx # Concierge thinking & rate lookup indicator
│   │   ├── SuggestedPrompts.tsx# Adaptive prompt chips based on conversation stage
│   │   └── ChatInput.tsx       # Multiline auto-expanding textarea with Enter to send
│   └── booking/
│       ├── BookingPanel.tsx    # Sidebar aggregator with guarantees & tips
│       ├── TripSummary.tsx     # Visual trip chips (Destination, Dates, Guests)
│       └── HoldStatusCard.tsx  # Live 15-minute countdown timer & locked rate
├── hooks/
│   ├── useChat.ts              # Conversation lifecycle, message dispatch, error recovery
│   └── useCountdown.ts         # Visual countdown with onExpire callback
├── services/
│   └── api.ts                  # Typed fetch client with ApiError parsing
├── styles/
│   └── design-tokens.css       # Obsidian, warm gold, and typography tokens
└── types/
    └── index.ts                # TypeScript contracts mirroring backend Pydantic models
```

---

## 3. Visual Design System
- **Color Tokens**:
  - Deep Obsidian Canvas: `--bg-main: #0c1017`
  - Elevated Cards: `--bg-surface-elevated: #1b2433`
  - Warm Hospitality Gold: `--accent-gold: #d4a373`, `--accent-gold-light: #faedcd`
  - Subtle Borders: `--border-subtle: rgba(255, 255, 255, 0.08)`
  - Status Accents: Emerald (`#10b981`), Amber (`#f59e0b`), Crimson (`#ef4444`)
- **Typography**: Clean serif headlines (`Playfair Display`, `Georgia`) combined with crisp sans-serif system fonts.

---

## 4. Key UX & Safety Patterns
1. **Zero Technical State Exposure**: Normal guests never see raw JSON or tool IDs. All data is translated into human-friendly trip plans and cards.
2. **Hold Protection on Reset**: If a guest clicks "New Stay" while holding an active room, an accessible confirmation modal warns them before discarding their hold.
3. **Adaptive Prompt Suggestions**: Chips adjust dynamically depending on what details are missing (e.g. initial suggestions $\to$ date selection $\to$ add-on requests).
4. **Resilient Error Recovery**: Network and business errors are rendered cleanly as system notices with actionable next steps.
