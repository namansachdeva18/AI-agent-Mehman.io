# Mehman.io — AI Hotel Booking Concierge

Mehman.io is a production-grade conversational AI hotel booking concierge for luxury Indian properties. It pairs **Google Gemini structured extraction** with an **authoritative SQLite database**, **deterministic tool execution**, a **multi-strategy recommendation engine**, and **persistent multi-turn state**.

---

## 🏛️ System Architecture

```
Guest Message
     │
     ▼
[ Intent & State Extraction ] (Gemini Structured Output + Offline Fallback)
     │
     ▼
[ Upstream State Invalidation ] (Destination / Date / Capacity mutation safety)
     │
     ▼
[ Deterministic Tool Execution ] (search_properties, check_availability, calculate_price, etc.)
     │
     ▼
[ Grounded Response Generation ] (Authoritative DB records, Zero Price Arithmetic)
     │
     ▼
[ State Persistence & Action Router ] (SQLite Session update + Move toward Booking Hold)
```

1. **Frontend:** React 19 + TypeScript + Vite + TailwindCSS with a dual-pane UI:
   - Left Pane: Luxury conversational concierge chat interface.
   - Right Pane: Real-time **Execution Trace**, **State Inspector**, and **Live 15-Minute Booking Hold Countdown Timer**.
2. **Backend:** FastAPI (Python 3.13) serving `/api/chat` with structured payload validation, asynchronous session persistence in SQLite, request correlation tracking (`X-Request-ID`), and standardized error envelopes.
3. **Database:** SQLite (WAL mode) containing 3 properties (Jaipur, Goa, Manali), 9 room types, verified amenities, cancellation policies, dynamic add-on services, and 365-day continuous inventory.

---

## 🚀 Quickstart & Setup Instructions

### 1. Backend Setup
```bash
cd backend
python -m venv venv

# Windows PowerShell:
venv\Scripts\activate

# Install dependencies:
pip install -r requirements.txt

# Seed the database:
python -m app.database.seed

# Run the FastAPI server:
venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## ⚙️ Environment Variables

Create a `.env` file in the `backend/` directory:

```env
# Google Gemini API Key (Optional — system automatically uses deterministic fallback if absent or rate-limited)
GEMINI_API_KEY=your_gemini_api_key_here

# Database Configuration
DATABASE_URL=sqlite:///mehman.db

# Server Configuration
HOST=127.0.0.1
PORT=8000
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

---

## 🧪 Testing & Evaluation

### Backend Unit & Agent Tests
```bash
cd backend
venv\Scripts\pytest tests/test_agent.py -v
venv\Scripts\python test_14_scenarios.py
```

### Evaluation Golden Dataset (18 Categories)
```bash
cd backend
venv\Scripts\pytest evals/ -v
```

### Frontend Tests
```bash
cd frontend
npm test
npm run build
```

---

## 📋 Assumptions & Design Decisions

1. **Single Source of Truth:** All room availability, pricing, amenities, and policies are strictly stored in SQLite. The LLM is never allowed to perform math or guess inventory.
2. **Deterministic Add-on Calculations:** Add-ons support 4 calculation models:
   - `PER_PERSON_PER_NIGHT` (e.g. Daily Buffet Breakfast)
   - `PER_ROOM_PER_NIGHT` (e.g. Room Heater)
   - `PER_PERSON_PER_STAY` (e.g. Royal Thali Dinner)
   - `PER_ROOM_PER_STAY` (e.g. Sunset Catamaran Cruise, Airport Pickup)
3. **Atomic 15-Minute Booking Holds:** Placing a hold decrements room inventory atomically with a 15-minute TTL. Self-hold replacement automatically cancels previous holds from the same session to prevent self-exhaustion of inventory.
4. **Upstream Invalidation:** Changing destination clears downstream rooms, holds, and property-specific add-ons. Changing dates clears active holds and re-checks availability.

---

## ⚠️ Known Limitations & Future Work

1. **Distributed Concurrency:** SQLite WAL mode handles local concurrency safely; for horizontally scaled multi-node clusters, Redis-based distributed locking (e.g. Redlock) would be used.
2. **Payment Gateway Integration:** The current system provides 15-minute `HELD` status reservations. Future iterations would integrate Stripe/Razorpay webhooks to transition holds to `CONFIRMED`.
3. **Multi-Room Group Bookings:** Parties requiring multiple separate rooms (e.g., 8 guests across two 4-person suites) currently require two bookings.
