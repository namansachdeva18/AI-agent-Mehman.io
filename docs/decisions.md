# Architectural Decisions Log

## ADR-001: Monorepo with Clean Separation
- **Decision**: Keep FastAPI backend and React frontend in a single repository.
- **Rationale**: Simplifies development and testing while preserving strict API boundary contracts.

## ADR-002: Official `google-genai` SDK
- **Decision**: Use the official Google GenAI SDK exclusively, isolated inside `app/llm/gemini.py`.
- **Rationale**: Avoids bloated third-party orchestrators (LangChain, LangGraph) and retains full control over prompts, schemas, and token usage.

## ADR-003: SQLite with WAL Mode as Authoritative Source of Truth
- **Decision**: SQLite with WAL mode, foreign keys, and strict normalization.
- **Rationale**: Zero external server dependencies for database; high read concurrency and atomic transactions with `busy_timeout = 15000`.

## ADR-004: Concurrency-Safe Booking Holds
- **Decision**: Execute atomic decrements `UPDATE availability SET available_units = available_units - 1 WHERE available_units > 0`.
- **Rationale**: Eliminates race conditions and prevents double-booking across multi-threaded concurrent hold requests.

## ADR-005: SQLite-Backed Persistent Conversation State
- **Decision**: Store `booking_state_json` and messages in normalized SQLite tables with optimistic version locking (`version = version + 1 WHERE version = ?`).
- **Rationale**: Conversations survive backend reboots and multiple client tabs with deterministic conflict detection.

## ADR-006: Deterministic 2-Stage Recommendation Engine (Phase 5)
- **Decision**: Implement candidate ranking in explicit Python rather than Gemini prompt reasoning.
- **Rationale**:
  1. **Deterministic Reproducibility**: Identical constraints and state always yield identical rankings.
  2. **Zero Price/Capacity Hallucinations**: Gemini cannot recommend non-existent hotels, invent fake rates, or recommend rooms with insufficient capacity.
  3. **Token & Cost Efficiency**: Performs only 1 model explanation call per recommendation instead of $N$ model calls for $N$ candidates.

## ADR-007: Budget Semantics (MAX vs TARGET vs FLEXIBLE)
- **Decision**: "Under ₹10,000" or "max ₹10,000" is treated as `BudgetMode.MAX` (hard filter), while "around ₹10,000" or "budget is ₹10,000" is treated as `BudgetMode.TARGET` (soft scoring preference).
- **Rationale**: Prevents discarding great hotel candidates when the user merely expresses a soft target while honoring hard ceiling constraints.

## ADR-008: Fresh Availability Validation Before Booking Hold
- **Decision**: Re-run `check_availability()` immediately before executing `create_booking_hold()`.
- **Rationale**: Recommendations reflect a point-in-time snapshot. Fresh validation ensures inventory hasn't been exhausted before locking in a hold.
