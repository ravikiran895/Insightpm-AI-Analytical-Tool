# InsightPM

**Self-hosted product analytics with AI-generated user behavior narratives.**

Funnels, retention, cohorts, and per-user AI storytelling — running on your own Firebase / GA4 BigQuery export. Built for product managers who want to understand their users, not just count them.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Node 20+](https://img.shields.io/badge/node-20%2B-green.svg)](https://nodejs.org/)
[![Tests](https://img.shields.io/badge/tests-117%20passing-brightgreen.svg)](#tests)

---

## What it does

Three things existing analytics tools don't do well:

1. **Per-user AI behavioral narratives** — Click any `user_pseudo_id` → an LLM writes their story, classifies their pattern (power user, drift-off, casual, etc.), and recommends what to investigate next.
2. **Insight investigator** — Click any fired insight → the tool runs ~6 targeted queries in parallel to dimensionalize it (concentration by country, platform, version, device) plus a day-by-day timeline, then asks an LLM to synthesize a hypothesis and recommended actions.
3. **Self-hosted on your data** — No vendor lock-in, no per-seat pricing, no LLM call limits beyond your own API key. The tool reads your Firebase Analytics BigQuery export directly.

---

## Why this exists

As a PM, I've used Firebase Analytics, Mixpanel, Amplitude, and MoEngage. Each is excellent at counting things. None of them tell me **why** a metric moved at the level of individual users.

You see "retention dropped 14%." The dashboard goes silent on which users dropped, what they were doing before, or where to start looking. You open five tabs, slice the funnel by three dimensions, eyeball user IDs, build a hypothesis. The work happens, just slowly.

The gap between "data" and "a direction worth pursuing" should be minutes, not hours.

The big SaaS players have AI features now — Mixpanel Spark, Amplitude Ask, PostHog Max. All answer aggregate questions. None generate a narrative for an individual user, because per-user LLM calls don't fit their unit economics. Running on your own data with your own API key changes the math.

---

## Quick start

> Prerequisites: Python 3.12, Node.js 20+, a Firebase project with BigQuery export enabled, and a GCP service account JSON with `BigQuery Data Viewer` + `BigQuery Job User` roles. See [REQUIREMENTS.md](REQUIREMENTS.md) for full setup.

**Option A — Docker (simplest)**

```bash
git clone https://github.com/YOUR_USERNAME/insightpm.git
cd insightpm
cp backend/.env.example backend/.env
# Edit backend/.env with your BigQuery project, dataset, and optional AI key
docker compose up -d
```

Open <http://localhost:5173>.

**Option B — Manual (Windows / PowerShell)**

```powershell
git clone https://github.com/YOUR_USERNAME/insightpm.git
cd insightpm

# Backend
cd backend
py -3.12 -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env with your values
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```powershell
cd insightpm\frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

Full step-by-step setup including service-account creation, BigQuery export enablement, and troubleshooting is in [SETUP.md](SETUP.md).

---

## Screenshots

Drop screenshots into `docs/screenshots/` and reference them here.

| | |
|---|---|
| **User Behavior Profile** — AI narrative for an individual user with metrics, pattern classification, and recommendations | `docs/screenshots/user-profile.png` |
| **Insight Investigator** — Multi-axis Where/When/Why/What analysis for any fired insight | `docs/screenshots/investigator.png` |
| **Architecture diagram** — How deterministic SQL and LLM narrative combine without the AI ever producing numbers | `docs/screenshots/architecture.png` |

---

## Features

### Core analytics
- Funnels with up to 10 steps, custom conversion windows (1–90 days), step suggestions
- Cohort retention with D1 / D7 / D30 metrics and per-day sparklines
- Top events explorer with bar visualizations
- Daily activity (DAU) trends

### Cohort filtering & breakdowns
- Filter every chart by country, platform, app version, or any user property — fields auto-discovered from your dataset
- Property breakdowns: split a funnel or retention chart by any property (top 5 values side-by-side)
- Saved cohorts: name and reuse cohort definitions

### Insights
- Rule-based insight engine: conversion changes, biggest funnel drop-offs, retention correlation (aha moment), event volume changes
- Severity-scored, color-coded by importance
- "Explain why" — AI hypothesis citing real numbers from your data
- "Investigate" — multi-axis Where/When/Why/What investigation with recommendations

### AI features (powered by Gemini or Claude)
- **User Behavior Profile** — AI surfaces the pattern for any individual user
- **Investigator** — turns a fired insight into a full investigation
- **Natural-language Ask** — "compare retention India vs US", "why is D7 dropping?"
- All AI features fall back to deterministic templates when no AI key is configured

### Shareability
- Shareable URLs — every view (date + cohort + funnel) encoded in the URL hash
- Saved funnels and saved cohorts, scoped per profile
- Multi-project support — one install handles every Firebase project you ship

### Production plumbing
- 117 unit tests, ~5-second suite
- Rotating logs at `~/.insightpm/logs/`
- Backup/restore CLI: `python -m app.backup backup`
- 5-minute query cache with per-call TTL
- "View SQL" button on every chart — no black box
- Optional shared-password protection for LAN/team deployments

---

## How it works

```
USER QUESTION
    ↓
DETERMINISTIC SQL  ← numbers come from here, 100% deterministic
    ↓
REAL DATA  ← fetched from your BigQuery
    ↓
LLM NARRATIVE  ← interpretation, never math
    ↓
YOU
```

The AI never produces numbers. Every metric on every chart comes from a SQL query you can inspect (via the "View SQL" button). The LLM's job is pattern-recognition and narrative — not arithmetic. This is the difference between AI that helps and AI that hallucinates, and it's defended in the architecture, not just the prompt.

For the full technical deep-dive see [ARCHITECTURE.md](ARCHITECTURE.md). For honest engineering decisions and what we deliberately chose not to build, see [TRADEOFFS.md](TRADEOFFS.md).

---

## Costs

- **BigQuery**: typical usage costs cents per session. Free tier covers most personal use.
- **AI provider**: roughly $0.001–0.005 per LLM call. Light/moderate use stays well within free tiers (Gemini Flash gives 1500 free requests/day).
- **Hosting**: $0 if running locally. A small VPS (~$5/month) if you want a shared instance for your team.

---

## Tests

```bash
cd backend
python -m pytest tests/
```

117 tests covering: cohort filter security (9 SQL-injection prevention tests), connection profile CRUD, saved funnels/cohorts, auth middleware, investigator math, retention rate calculation, user profiler, LLM client, anomaly explainer, insight engine, and cache TTL.

---

## Documentation

| Document | When to read |
|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | Before installing — what you need on your machine |
| [SETUP.md](SETUP.md) | Step-by-step first-time setup (BigQuery, service account, env vars) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Understanding how the code is organized and why |
| [TRADEOFFS.md](TRADEOFFS.md) | Engineering decisions — what we chose, what we deferred |
| [SECURITY.md](SECURITY.md) | Security model, what's protected, what isn't |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Filing issues, opening PRs, dev environment |
| [CHANGELOG.md](CHANGELOG.md) | What's changed in each release |

---

## Project status

Active development. Current version: **v0.9.2**.

This is a personal project shared in the hope it's useful. No SLA, no support guarantees. Issues and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

[MIT](LICENSE). Use it, modify it, ship it. Attribution appreciated but not required.

---

## Acknowledgements

Built with Anthropic's Claude as a pair programmer — architecture decisions, SQL design, security reviews, and debugging. Also the AI behind the user-narrative and investigation features in production.
