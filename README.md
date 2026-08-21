# Mehman.io — AI Hotel Booking Concierge (Mira)

[![Live Web App](https://img.shields.io/badge/Vercel-Live%20App-black?logo=vercel)](https://ai-agent-mehman-io.vercel.app)
[![Live Backend API](https://img.shields.io/badge/Render-FastAPI%20Backend-blue?logo=render)](https://ai-agent-mehman-io.onrender.com/health)
[![Tests](https://img.shields.io/badge/Tests-19%2F19%20Passing-brightgreen)](https://github.com/namansachdeva18/AI-agent-Mehman.io)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19.0-61dafb?logo=react)](https://react.dev/)

Mehman.io is a production-grade conversational AI hotel booking concierge for luxury Indian properties. It pairs **Google Gemini structured extraction** with an **authoritative SQLite database**, **deterministic tool execution**, a **multi-strategy recommendation engine**, and **persistent multi-turn state**.

* **🌐 Live Web Application:** [https://ai-agent-mehman-io.vercel.app](https://ai-agent-mehman-io.vercel.app)
* **⚡ Live Backend API:** [https://ai-agent-mehman-io.onrender.com](https://ai-agent-mehman-io.onrender.com)

---

## 🏛️ System Architecture

```
                               ┌────────────────────────┐
                               │   Guest User (Chat)    │
                               └───────────┬────────────┘
                                           │ HTTP POST /api/chat
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ FastAPI Application Layer                                                    │
│  - Correlation Middleware (X-Request-ID tracking)                            │
│  - Pydantic Payload Validation & Error Envelopes                             │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Agent Orchestrator (Decision & Intent Layer)                                 │
│  1. Semantic Extraction: Gemini Flash / Structured JSON Schema Output        │
│  2. Invariant & Invalidation Pipeline (State Transition Rules)               │
│  3. Action Router & Missing Information Clarifier                            │
└──────────────────┬─────────────────────────────────────┬─────────────────────┘
                   │                                     │
                   ▼ Tool Dispatch                       ▼ State & History
┌──────────────────────────────────────┐ ┌─────────────────────────────────────┐
│ Deterministic Tool Execution Engine  │ │ SQLite Authoritative Store          │
│  • search_properties()               │ │  • Properties, Rooms, Amenities    │
│  • check_availability()              │ │  • Dynamic Pricing & Add-ons       │
│  • get_room_details()                │ │  • 365-Day Inventory Units         │
│  • calculate_price() (Zero LLM Math) │ │  • Booking Holds (15-min TTL)      │
│  • create_booking_hold() (Atomic)    │ │  • Conversation History & State     │
└──────────────────────────────────────┘ └─────────────────────────────────────┘
```

1. **Frontend (React 19 + TypeScript + Vite + TailwindCSS):**
   - **Dual-Pane Observability:** Luxury guest chat interface paired with an interactive **Execution Trace**, **State Inspector**, and live **15-Minute Countdown Timer**.
2. **Backend (FastAPI + Python 3.13):**
   - Async endpoints with unified error handling (`AppError`), correlation tracking (`X-Request-ID`), and standardized JSON response envelopes.
3. **Database (SQLite in WAL Mode):**
   - Single source of truth containing 3 partner properties (Jaipur, Goa, Manali), 9 room types, verified amenities, cancellation policies, dynamic add-on services, and 365-day continuous inventory.

---

## 🔁 The Core Agent Flow

Every user utterance strictly executes through a deterministic 7-stage cycle:
$$\text{Guest message} \xrightarrow{} \text{update state} \xrightarrow{} \text{decide next action} \xrightarrow{} \text{call tool} \xrightarrow{} \text{validate result} \xrightarrow{} \text{respond naturally} \xrightarrow{} \text{continue toward booking}$$

---

## 🚀 Quickstart & Setup Instructions

### 1. Prerequisites
* Python 3.11+
* Node.js 18+

### 2. Backend Setup
```bash
cd backend
python -m venv venv

# Activate Virtual Environment:
# On Windows PowerShell:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies:
pip install -r requirements.txt

# Seed the database:
python -m app.database.seed

# Run the FastAPI server:
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## ⚙️ Environment Variables

Create a `.env` file in the `backend/` directory (see `backend/.env.example`):

```env
# Google Gemini API Key (Optional — system automatically uses deterministic fallback if absent or rate-limited)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash

# Database Configuration
DATABASE_URL=sqlite:///data/mehman.db

# Server Configuration
ENVIRONMENT=development
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000
```

---

## 🧪 Testing & Evaluation

### Backend Unit & Agent Tests
```bash
cd backend
pytest tests/test_agent.py -v
```

### Golden Dataset Evaluation (18 Test Categories)
```bash
cd backend
pytest evals/ -v
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
