# Mehman.io Production Deployment & Operations Guide

## 1. System Overview
Mehman.io is a luxury AI hotel booking concierge composed of:
- **Frontend**: React 19 + TypeScript single-page application built with Vite.
- **Backend**: FastAPI (Python 3.11+) asynchronous REST service.
- **Database**: SQLite with WAL mode, foreign keys, and atomic inventory transactions.
- **AI Agent**: Google Gemini (`gemini-3.6-flash`) structured intent extraction and grounded responses.

---

## 2. Production Prerequisites

### Backend Requirements
- **Python**: 3.11, 3.12, or 3.13
- **Virtual Environment**: Recommended (`venv` or containerized)
- **Dependencies**: `pip install -r backend/requirements.txt`
- **Environment Variables** (`backend/.env`):
  ```env
  GEMINI_API_KEY=AIzaSy...
  GEMINI_MODEL=gemini-3.6-flash
  ENVIRONMENT=production
  DEBUG=false
  DATABASE_URL=sqlite:///data/mehman.db
  ALLOWED_ORIGINS=["https://your-frontend-domain.com"]
  ```

### Frontend Requirements
- **Node.js**: 18+ or 20+
- **Package Manager**: `npm`
- **Dependencies**: `npm install` (in `frontend/`)
- **Environment Variables** (`frontend/.env.production`):
  ```env
  VITE_API_BASE_URL=https://your-api-domain.com
  ```

---

## 3. Deployment Procedure

### Step 1: Database Initialization
Run the authoritative database seeding script **explicitly once** prior to launch:
```bash
cd backend
venv\Scripts\python -m app.database.seed
```
> [!IMPORTANT]
> The application startup does NOT automatically reseed or wipe the database. Seeding is an explicit, safe administrative operation.

### Step 2: Backend Startup (Production)
Run FastAPI with Uvicorn (or Gunicorn with Uvicorn workers):
```bash
cd backend
venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### Step 3: Frontend Production Build & Hosting
Compile optimized static assets:
```bash
cd frontend
npm run build
```
Host the generated `frontend/dist/` directory on any static web host (e.g., Nginx, Cloudflare Pages, Vercel, S3/CloudFront).

---

## 4. SQLite Persistence & Backup Strategy

### Filesystem Storage Warning
> [!WARNING]
> **Ephemeral Storage Limitation**: If deploying the backend to container platforms with ephemeral storage (e.g., standard serverless containers without attached persistent volumes), SQLite database files will reset upon container restart. For persistent state, mount a persistent volume to `/data/` or host on a persistent VPS/VM instance.

### Safe WAL-Mode Backup Process
To take a zero-downtime backup of the live SQLite database:
1. Use SQLite's online backup API via CLI:
   ```bash
   sqlite3 data/mehman.db ".backup 'data/backup_mehman_$(date +%Y%m%d_%H%M%S).db'"
   ```
2. Or use Python's built-in `sqlite3.Connection.backup()`:
   ```python
   import sqlite3
   src = sqlite3.connect("data/mehman.db")
   dst = sqlite3.connect("data/backup_mehman.db")
   src.backup(dst)
   dst.close()
   src.close()
   ```
3. Backup Frequency: Daily for configuration/hotels; hourly snapshots for active conversation holds.

---

## 5. Security & Rate Limiting Guidelines
- **API Keys**: `GEMINI_API_KEY` is strictly confined to the backend server. It is never transmitted to the browser.
- **CORS**: Ensure `ALLOWED_ORIGINS` is configured to the exact frontend production origin (never `*` in production).
- **Reverse Proxy Rate Limiting**: In production deployments, configure Nginx / Cloudflare / Traefik reverse proxies to rate-limit `POST /api/chat` (e.g., 20 requests/minute per IP) to mitigate denial-of-wallet / API exhaustion attacks.
