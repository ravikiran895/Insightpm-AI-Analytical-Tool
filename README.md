# InsightPM

Self-hosted product analytics on top of your Firebase / GA4 BigQuery export.
Funnels, retention, cohorts, breakdowns, AI-generated user behavior narratives.

Built for PMs who want to understand their users, not just count them.

---

## Quick start (Docker — recommended)

**Requirements:** Docker Desktop (Windows/Mac) or Docker Engine (Linux). Nothing else.

1. **Configure your environment.** Copy `backend/.env.example` to `backend/.env`,
   then edit it with your GCP project details and (optionally) AI keys:

   ```
   BQ_PROJECT_ID=your-firebase-project-id
   BQ_DATASET_ID=analytics_123456789
   FRONTEND_ORIGIN=http://localhost:5173

   # Optional but recommended -- enables AI features:
   GEMINI_API_KEY=AIza...
   # or
   ANTHROPIC_API_KEY=sk-ant-...

   # Optional -- enables shared password protection:
   INSIGHTPM_PASSWORD=your-shared-password
   ```

2. **Place your service account JSON file** somewhere accessible, then either:
   - Set `GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json` in `.env` (if you mount the file as a volume), OR
   - Paste the JSON content inline as `GCP_SERVICE_ACCOUNT_JSON=...` in `.env`, OR
   - Add a connection profile via the UI after first launch (recommended)

3. **Start everything:**

   ```
   docker compose up -d
   ```

   First run takes ~3 minutes to build images. Subsequent starts are instant.

4. **Open** http://localhost:5173 and follow the connection wizard.

To update later:
```
git pull   # or unzip a new release
docker compose up -d --build
```

To stop:
```
docker compose down
```

To wipe all data (saved profiles, funnels, cohorts):
```
docker compose down -v
```

---

## Manual setup (without Docker)

If you prefer running directly on your machine:

### Backend

```
cd backend
python3.12 -m venv venv
venv\Scripts\Activate.ps1   # Windows
source venv/bin/activate    # Linux/Mac

pip install -r requirements.txt
cp .env.example .env        # then edit .env with your values

uvicorn app.main:app --reload --port 8000
```

### Frontend

In a separate terminal:

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

---

## Features

### Core analytics
- **Funnels** with up to 10 steps, custom conversion windows (1-90 days), step suggestions from your data
- **Cohort retention** with D1/D7/D30 metrics + per-day sparklines
- **Top events explorer** with bar visualizations
- **Daily activity** (DAU) trends

### Cohort filtering & breakdowns
- Filter every chart by country, platform, app version, or any user property — fields auto-discovered from your dataset
- **Property breakdowns**: split a funnel or retention chart by any property (top 5 values side-by-side)
- **Saved cohorts**: name and reuse cohort definitions

### Insights
- Rule-based insight engine: conversion changes, biggest funnel drop-offs, retention correlation (aha moment), event volume changes
- Severity-scored, color-coded by importance
- **💡 Explain why** — AI-generated hypothesis citing real numbers from your data
- **🔍 Investigate** — full Where/When/Why/What multi-axis investigation with recommendations

### User Behavior Profiling (USP)
- Pick any `user_pseudo_id` → get an AI-generated story of what they did, when, and why
- Pattern classification (power user, returning, drift-off, casual, etc.)
- Recommended actions per user pattern
- Full event journey timeline

### Natural-language Ask box
- "compare retention India vs US"
- "why is retention low"
- "what's the aha moment"
- Falls back to keyword routing if no AI key configured

### Shareability
- **Shareable URLs**: every view (date + cohort) encoded in the URL
- **Saved funnels** and **saved cohorts**, scoped per profile
- Multi-project support: one install handles every Firebase project you ship

### Production plumbing
- 112 unit tests
- Rotating logs at `~/.insightpm/logs/`
- Backup/restore CLI: `python -m app.backup backup`
- 5-minute query cache (per-call TTL configurable)
- "View SQL" button on every chart
- Optional shared-password protection

### AI providers
Works with either provider, falls back to deterministic templates if neither is configured:

- **Gemini** (recommended for free tier — 1500 requests/day on Flash 2.0)
- **Anthropic Claude** (~$0.001 per LLM call with Haiku)

---

## Costs

- **BigQuery:** typical usage costs cents per session. Free tier covers most personal use.
- **AI provider:** ~$0.001-0.005 per LLM call. Light/moderate use stays well within free tiers.
- **Compared to SaaS:** Mixpanel/Amplitude/MoEngage typically charge $200-2000+/month per seat.

---

## Architecture

- **Backend:** FastAPI + Pydantic, raw SQLite (no ORM), in-memory TTL cache
- **Frontend:** React 18 + Vite + Recharts, no global state library
- **AI:** unified abstraction over Gemini Flash and Claude Haiku, with a topic guardrail
- **Security:** parameterized BigQuery queries, allowlisted cohort filter fields, optional password gate

For internals, see code comments — every service module starts with a design rationale.

---

## License

MIT. Use it, modify it, ship it.
