# Phase 10 Failure Recovery Matrix

| Failure Mode | Detection Mechanism | User Experience | Recovery Strategy | Data Integrity Guarantee | Retry Behavior |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Gemini API Timeout** | `asyncio.wait_for(timeout=10.0)` | Seamless response using deterministic fallback analyzer | Immediate transparent fallback | 100% DB grounded; no corrupted state | 0 blind retries on state-changing actions |
| **Gemini HTTP 429 (Rate Limit)** | HTTP status code check in `GeminiProvider` | Polite assistant guidance with rule-based fallback response | Fallback analyzer processes query | State preserved in SQLite | Backoff & deterministic fallback |
| **Database Lock / Busy** | SQLite `OperationalError` / `DatabaseBusy` | Friendly retry notice ("System momentarily busy") | SQLite WAL mode + busy timeout retry | ACID transaction isolation prevents partial writes | Exponential backoff (up to 3 attempts) |
| **Booking Hold Race Condition** | `available_units = 0` check in atomic UPDATE | "Room was just booked by another guest. Recommending alternatives." | Surfaces alternative available rooms | Inventory never drops below 0 | Prompt user for alternative room |
| **Availability Expiry / Conflict** | Pre-hold fresh validation check | Clear notification that room is no longer available | Guides user to alternative dates/rooms | Prevents invalid hold creation | Re-fetch fresh availability |
| **Hold Expiration during Session** | `hold_expires_at <= now()` check | Countdown badge displays "Expired"; hold card offers instant re-search | `release_expired_holds()` frees inventory | Inventory restored exactly once | User prompted to re-hold if units available |
| **Missing / Lost Session** | Conversation lookup returns `None` | Automatically initializes fresh conversation with welcome hero | Graceful restart | No orphaned records | Fresh session ID issued |
| **Network Interruption / Disconnect**| Frontend `fetch` error caught in `useChat` hook | Error toast with retry button; input preserved | Client retains uncommitted input | No duplicate message dispatched | Safe manual retry |
