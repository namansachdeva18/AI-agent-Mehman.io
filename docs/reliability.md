# Mehman.io Reliability & Failure Recovery Guide

## 1. Safety Principles & Ingress Boundaries
- **Hierarchy of Authority**:
  $$\text{User Input} \to \text{Gemini Interpretation} \to \text{Pydantic Schema Validation} \to \text{Deterministic Logic} \to \text{SQLite Database}$$
- **Ingress Protections**:
  - Max message length limit: 10,000 characters.
  - Empty / whitespace-only messages rejected with HTTP 400 `INVALID_REQUEST`.
  - Request Correlation ID (`X-Request-ID`) attached to every API request and propagated to logs and error payloads.

---

## 2. Failure Modes, Edge Cases & Recovery

| Failure Mode | Severity | System Behavior | Recovery Strategy |
| :--- | :---: | :--- | :--- |
| **Gemini API Timeout / Quota 429** | Moderate | Trapped in `GeminiProvider`; returns `LLM_ERROR` (`retryable: True`). Orchestrator falls back to deterministic rule extraction. | Frontend displays retryable prompt; system continues operating deterministically. |
| **Malformed LLM Output** | Low | Pydantic schema validation rejects invalid fields (e.g. `guests = -50`). | Falls back to rule-based parser or asks user for clarification. |
| **Dates Outside Inventory** | Low | Validates against `2026-09-01` to `2027-08-31`. | Informs user of exact inventory coverage window without fabricating dates. |
| **Checkout $\le$ Check-in** | Low | Strict validator in `BookingState` and `CheckAvailabilityInput` raises `INVALID_DATES`. | Returns friendly clarification asking for valid chronological dates. |
| **Guest Capacity Violation** | Low | If guest count increases beyond room capacity (e.g. 2 $\to$ 5 for a 2-guest room), room selection and holds are cleared immediately. | Orchestrator prompts user to choose from suitable 5-guest rooms. |
| **Concurrent Booking Race on Last Unit** | Critical | Atomic SQLite decrement `SET available_units = available_units - 1 WHERE available_units > 0`. | Exactly 1 request acquires hold; the other receives HTTP 409 `UNAVAILABLE_ROOM`. No negative inventory. |
| **Hold Expiration** | Moderate | `release_expired_holds()` restores inventory atomically and updates status to `EXPIRED`. | Idempotent; repeated invocations release 0 additional units. |
| **Hold Cancellation** | Moderate | `cancel_booking_hold()` validates `status == 'HELD'` before restoring inventory. | Idempotent; duplicate cancellations return `False` without double-restoration. |
| **Stale State on Destination Switch** | Low | Destination change (Goa $\to$ Jaipur) clears `selected_property_id`, `selected_room_id`, `hold_id`, `hold_total_price`. | Prevents booking a Goa room under Jaipur trip state. |
| **Completed / Abandoned Conversation** | Low | Closed conversation rejects new mutations with HTTP 400 `CONVERSATION_CLOSED`. | Directs guest to start a new booking session. |

---

## 3. Concurrency & Locking Strategy
- **Optimistic State Locking**: `UPDATE conversations SET ... version = version + 1 WHERE id = ? AND version = ?`. Conflicting concurrent requests receive HTTP 409.
- **SQLite Concurrency**: Database runs in WAL mode with `PRAGMA busy_timeout = 15000` and thread-isolated connections.
