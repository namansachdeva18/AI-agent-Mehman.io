# Mehman.io Idempotency Audit & Guarantees

## 1. Idempotency Classification

| Operation | Category | Idempotency Mechanism | Failure & Retry Safety |
| :--- | :--- | :--- | :--- |
| **`search_properties`** | Naturally Idempotent | Read-only SQL query against properties & rooms | Completely safe to retry indefinitely |
| **`check_availability`** | Naturally Idempotent | Read-only SQL query against availability table | Completely safe to retry |
| **`get_room_details`** | Naturally Idempotent | Read-only SQL query with JOINs on amenities/policies | Completely safe to retry |
| **`calculate_price`** | Naturally Idempotent | Read-only mathematical calculation over nightly rates & add-ons | Completely safe to retry |
| **`create_booking_hold`** | Explicitly Idempotent | Session hold check & atomic hold transition. If hold already active for session/room, reuses or rejects | Blind retries avoided; fresh availability verified |
| **`cancel_booking_hold`** | Explicitly Idempotent | Updates status `ACTIVE` $\to$ `CANCELLED` only where `status = 'ACTIVE'`; double-restore prevented | Safe to retry; inventory restored exactly once |
| **`release_expired_holds`**| Explicitly Idempotent | Updates status `ACTIVE` $\to$ `EXPIRED` only where `status = 'ACTIVE'`; double-restore prevented | Safe to run repeatedly in background loops |
| **`update_booking_state`**| Guarded by Optimistic Locking | Version check `version = current_version` | Prevents lost updates under concurrent message edits |
