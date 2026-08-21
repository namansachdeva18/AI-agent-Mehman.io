# E2E Testing Architecture & Guide — Mehman.io

## 1. Overview
Mehman.io uses [Playwright](https://playwright.dev/) for real browser end-to-end (E2E) testing across Desktop and Mobile viewports. These tests validate the full stack with real network calls:
- **Frontend**: React 19 + TypeScript on Vite dev server (`http://127.0.0.1:5173`).
- **Backend**: FastAPI on Uvicorn daemon (`http://127.0.0.1:8000`).
- **Database**: SQLite with seed hotel data.
- **AI Agent**: Google Gemini API via `gemini-3.6-flash` model.

---

## 2. Test Suites

The test files reside in `frontend/e2e/`:
1. `booking-flow.spec.ts`:
   - **Journey 1**: Initial page load, header, tagline, suggested prompts, and trip summary initial state.
   - **Journey 2 & 3**: Conversational search (Goa, 5 guests, 2026-09-10 to 2026-09-13), room selection, and deterministic pricing quote with daily breakfast add-on.
   - **Journey 4 & 5**: 15-minute booking hold creation with real-time countdown timer, locked price, and browser page refresh state restoration.
   - **Journey 8**: System prompt override & injection resistance in the real browser DOM.
   - **Journey 9**: Natural language parameter corrections (e.g. updating guest count from 4 to 6).
   - **Security Audit**: Verification that zero API keys (`AIzaSy`, `SECRET_KEY`) exist in the browser DOM.

2. `accessibility-and-edge.spec.ts`:
   - **Keyboard Navigation & Accessibility**: Textarea focus, Enter-to-submit, Shift+Enter multiline.
   - **Rapid Submission / Double Click Guard**: Button spam protection preventing duplicate holds or desynchronization.
   - **Responsive Viewport Testing**: Validation across 1440×900 (Desktop), 1024×768 (Tablet), 430×932 (Large Mobile), 390×844 (Mobile), and 375×667 (Compact Mobile).
   - **Network Security Audit**: Intercepting all browser network requests to verify that frontend strictly calls the FastAPI backend and never calls Google Gemini or SQLite directly.

---

## 3. Running the E2E Suite

### Prerequisites
1. Ensure the FastAPI backend is running:
   ```bash
   cd backend
   venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
2. Verify backend connectivity:
   ```bash
   powershell -Command "(Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health') | ConvertTo-Json"
   ```

### Execution
Run all Playwright tests across Desktop and Mobile viewports:
```bash
cd frontend
npm run test:e2e
```

Run in headed mode for visual observation:
```bash
npx playwright test --headed
```

---

## 4. Invariants Tested
- **Zero Client-Side Math**: React never computes stay totals or hold expirations.
- **Physical Inventory Locking**: Holds lock inventory atomically and release upon backend expiration.
- **Session Persistence**: Browser `localStorage` contains only `mehman_session_id`.
