# Mehman.io System Architecture

## Overview
Mehman.io is an AI-powered conversational hotel booking assistant for Indian hotel properties. It integrates natural language understanding via Google Gemini with deterministic, hallucination-free hotel data, pricing calculations, inventory management, persistent conversations, and recommendation intelligence in SQLite.

---

## High-Level Architecture (Phases 1–5)

```
                            ┌────────────────────────────────────────┐
                            │        Frontend Client (React 19)      │
                            │  - Conversational Booking Interface    │
                            │  - Live BookingState Inspector         │
                            │  - Tool Execution & Event Trace Log    │
                            └───────────────────┬────────────────────┘
                                                │ REST API (JSON)
                                                ▼
                            ┌────────────────────────────────────────┐
                            │         FastAPI Web Backend            │
                            │  - GET /health                         │
                            │  - POST /api/chat                      │
                            │  - /api/conversations/* REST Suite     │
                            └───────────────────┬────────────────────┘
                                                │
                                                ▼
                            ┌────────────────────────────────────────┐
                            │           AgentOrchestrator            │
                            │  1. Retrieve & validate state / history│
                            │  2. Gemini NLU & Intent Extraction     │
                            │  3. Stale State Invalidation           │
                            │  4. Missing Information Gating         │
                            └───────┬────────────────────────┬───────┘
                                    │                        │
                     Intent & Patch │                        │ Tool Calls & Recommendation
                                    ▼                        ▼
     ┌────────────────────────────────┐            ┌────────────────────────────────────────┐
     │         GeminiProvider         │            │              ToolExecutor              │
     │  (google-genai SDK / JSON mode)│            │  - Strict 5-Tool Allowlist             │
     └────────────────────────────────┘            │  - Pydantic Schema Arg Validation      │
                                                   │  - Latency Measurement & Error Trapping│
                                                   └───────────────────┬────────────────────┘
                                                                       │
                                                   ┌───────────────────┴────────────────────┐
                                                   │                                        │
                                                   ▼                                        ▼
                               ┌────────────────────────────────┐       ┌────────────────────────────────┐
                               │   Deterministic Hotel Tools    │       │     RecommendationEngine       │
                               │  - search_properties()         │       │  - Stage 1: Hard Filtering     │
                               │  - check_availability()        │       │  - Stage 2: 5-D Scoring & Rank │
                               │  - get_room_details()          │       │  - 6 Ranking Strategies        │
                               │  - calculate_price()           │       │  - compare_rooms() Service     │
                               │  - create_booking_hold()       │       │  - Relaxed Alternative Matches │
                               └───────────────┬────────────────┘       └───────────────┬────────────────┘
                                               │                                        │
                                               ▼                                        ▼
                               ┌────────────────────────────────────────────────────────────────────────┐
                               │                   Authoritative SQLite Database                        │
                               │      (WAL Mode, Foreign Keys, 11 Normalized Tables, Busy Timeout)      │
                               │   - properties, rooms, amenities, availability, booking_holds, etc.   │
                               │   - conversations, conversation_messages (Sequential & Versioned)      │
                               └────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Recommendation Engine (`app/recommendations/`)
- **Stage 1: Hard Constraint Filtering**:
  - Eliminates rooms that violate destination, capacity, stay date availability, or explicit maximum budget ceilings (`budget_mode == BudgetMode.MAX`).
- **Stage 2: Deterministic 5-Dimension Scoring ($0.0 \to 1.0$)**:
  - `quality_score`: Star rating and room size normalized.
  - `capacity_fit`: $1.0 - 0.1 \times (\text{max\_guests} - \text{guests})$.
  - `value_score`: Quality/size relative to nightly rate.
  - `amenity_match`: Fraction of requested amenities matched via alias dictionary.
  - `preference_match`: Traveler profile alignment (`FAMILY`, `LUXURY`, `BUDGET`, `COUPLE`, `STANDARD`).
- **Ranking Strategies**: `BEST_MATCH`, `CHEAPEST`, `BEST_VALUE`, `LUXURY`, `FAMILY`, `PRICE_LOW_TO_HIGH`.
- **Comparison Service**: Side-by-side structured comparison of 2 or 3 rooms across prices, stay totals, amenities, policies, and key differences.

### 2. LLM Reasoning Layer (`app/llm/gemini.py` & `app/agent/prompts.py`)
- Isolated to the official `google-genai` SDK.
- Responsible exclusively for user intent understanding, state patch extraction, and natural-language explanations of deterministic tool/ranking results.
- **Strict Grounding Rule**: Gemini is prohibited from inventing hotel facts, room types, pricing calculations, availability, or ranking orders.

### 3. Persistent Conversation State (`app/services/conversation.py`)
- SQLite-backed state persistence storing `booking_state_json`, optimistic `version` concurrency lock, and active hold IDs.
- Chronological message history with monotonically increasing sequence numbers.
- Automated hold reconciliation ensuring expired/cancelled holds are cleared from state.

### 4. Deterministic Tools (`app/tools/`)
- `search_properties()`: Strict AND amenity filtering, budget and guest limits.
- `check_availability()`: Nightly inventory validation with checkout-date exclusivity.
- `get_room_details()`: Clean domain models for room specs, policies, and add-ons.
- `calculate_price()`: Itemized night-by-night seasonal pricing and 4 add-on pricing models.
- `create_booking_hold()`: Atomic concurrency-safe inventory decrements (`available_units = available_units - 1 WHERE available_units > 0`) with 15-minute expiration.

### 5. Production Frontend Interface (`frontend/src/`)
- **React 19 + TypeScript + Vite**: Responsive client with modular component architecture (`HotelCard`, `RoomCard`, `PriceBreakdown`, `BookingHoldCard`, `BookingPanel`).
- **Deterministic UI Rendering**: All prices, capacity calculations, and availability statuses are rendered directly from backend payload responses without client-side mathematical recalculations.
- **Session Persistence**: Backed by `localStorage.mehman_session_id` and restored via `/api/conversations/{id}`.
- **Visual Hold Countdown**: Real-time 15-minute countdown timer linked to backend `expires_at` with expired inventory release states.

### 6. Security & Trust Boundaries
- **GEMINI_API_KEY Containment**: Confined exclusively to the backend Python runtime. Never accessible by frontend client or browser network inspection.
- **Authoritative Database Boundaries**: The frontend and LLM have zero direct SQLite write access. All inventory decrements occur exclusively inside atomic transaction blocks in `app/tools/booking.py`.
- **CORS Isolation**: Environment-driven CORS configuration preventing cross-origin request spoofing in production environments.

