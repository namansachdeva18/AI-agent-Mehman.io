# Phase 6 Audit: Edge Cases, Reliability & Agent Safety

## 1. Executive Summary
This audit evaluates the reliability, edge-case safety, and boundary defenses of Mehman.io across Phases 1–5. It identifies potential failure points in conversational interpretation, API input validation, state transitions, concurrency, and LLM isolation, providing concrete architectural mitigations for Phase 6.

---

## 2. Component Audits & Gap Analysis

### A. API Ingress & Input Validation
- **Current State**: `POST /api/chat` and `/api/conversations/*` accept payloads without message length caps or request correlation tracking.
- **Identified Risks**:
  - Excessively large payloads (>10KB) could overwhelm LLM context windows or cause denial of service.
  - Empty/whitespace messages (`""`, `"   "`) trigger unnecessary downstream processing.
  - Lack of a unique correlation ID per request hinders cross-tier debugging.
- **Mitigation**:
  - Add request validation middleware and Pydantic field constraints (`min_length=1`, `max_length=10000`).
  - Introduce `X-Request-ID` correlation middleware and attach it to logs and standardized error responses.
  - Enhance `AppError` with a `retryable: bool` property and standardize error response payloads.

### B. LLM Provider & Failure Isolation
- **Current State**: `GeminiProvider` catches exceptions and raises `AppError(LLM_ERROR)`. `AgentOrchestrator` falls back to deterministic rule analysis when Gemini is unconfigured or fails.
- **Identified Risks**:
  - Gemini API timeouts, quota limits (HTTP 429), or retired model names could lead to unhandled exceptions or expose internal stack traces.
  - Malformed JSON from LLM could corrupt booking state if not strictly validated against Pydantic schemas.
- **Mitigation**:
  - Catch network, timeout, JSON decoding, and HTTP exceptions in `GeminiProvider` and return safe user-facing fallbacks.
  - Enforce strict Pydantic model validation on all extracted state patches and agent decisions.
  - Prohibit LLM from directly assigning booking IDs, pricing calculations, or hold confirmations.

### C. BookingState & Upstream Dependency Invalidation
- **Current State**: Destination changes clear room selections and holds. Date changes clear holds.
- **Identified Risks**:
  - Increasing guest count (e.g. 2 $\to$ 5) while keeping a 2-guest room selected could allow holding an under-capacity room.
  - Lowering budget ceiling below the selected room's rate could leave an invalid selection active.
  - Inconsistent `adults + children != guests` could lead to contradictory capacity checks.
- **Mitigation**:
  - Add guest count capacity re-validation in `AgentOrchestrator`: if `new_guests > selected_room.max_guests`, immediately invalidate `selected_room_id`.
  - Add `adults + children == guests` consistency validation in `BookingState`.
  - Invalidate recommendation cache and holds whenever destination, dates, or guests change.

### D. Booking Safety & Hold Lifecycle Transitions
- **Current State**: `create_booking_hold` performs atomic decrements. Hold reconciliation clears expired holds.
- **Identified Risks**:
  - Double booking requests from frontend retries could attempt duplicate holds.
  - Invalid hold status transitions (e.g. trying to transition `CANCELLED -> HELD` or `EXPIRED -> HELD`).
- **Mitigation**:
  - Enforce explicit state transition state machine: `HELD -> EXPIRED`, `HELD -> CANCELLED`, `HELD -> CONFIRMED`.
  - Validate fresh availability and fresh pricing immediately before calling `create_booking_hold`.
  - Make hold cancellation and expiration releases strictly idempotent.

---

## 3. Implementation Plan for Phase 6
1. **Error Model & Middleware**:
   - Update `app/errors.py` with `retryable` flag and standardized JSON structure.
   - Add request correlation ID middleware in `app/main.py`.
2. **Input Validation**:
   - Update `ChatRequest` in `app/api/routes/chat.py` with `min_length=1, max_length=10000`.
   - Update `BookingState` in `app/agent/schemas.py` with adult/child consistency and guest capacity validation.
3. **Orchestrator Hardening**:
   - Invalidate room selection if guest count increases beyond room capacity.
   - Handle ambiguous context references ("the first one", "second option") deterministically against recent recommendation history.
   - Handle unrelated queries ("What is the capital of France?") without mutating hotel state.
4. **Hold State Machine & Idempotency**:
   - Enforce valid hold status transitions in `app/tools/booking_hold.py`.
5. **Comprehensive Test Suite**:
   - Create `backend/tests/test_edge_cases.py` covering all 36 specified edge cases.
   - Create `docs/reliability.md` documenting failure modes, concurrency, and recovery strategies.
