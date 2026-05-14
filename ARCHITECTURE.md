# Architecture

A technical deep-dive into how InsightPM is organized. Read this if you want to modify the code, contribute features, or understand the design before deploying.

For the higher-level "why" behind decisions, see [TRADEOFFS.md](TRADEOFFS.md).

---

## At a glance

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (React)                                                │
│  - Dashboard, Funnel, Retention, User Profile, Investigator     │
│  - URL hash encodes shareable state (date + cohort + funnel)    │
│  - Auth digest in sessionStorage (cleared on tab close)         │
└────────────────────────┬────────────────────────────────────────┘
                         │ JSON over HTTP (X-InsightPM-Auth header)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI backend                                                │
│  ┌──────────────┬─────────────┬──────────────┬───────────────┐  │
│  │   Routers    │   Services  │  SQL files   │  Tests        │  │
│  │ (HTTP layer) │ (business)  │ (templates)  │ (117 passing) │  │
│  └──────────────┴─────────────┴──────────────┴───────────────┘  │
│  + 5-min TTL cache, rotating logger, SQLite for profiles       │
└────────────────────────┬────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   ┌─────────┐     ┌──────────┐     ┌──────────────┐
   │ BigQuery│     │  SQLite  │     │  Gemini /    │
   │ (data)  │     │ (config) │     │  Anthropic   │
   └─────────┘     └──────────┘     └──────────────┘
```

**Three external dependencies:**
- **BigQuery** — your Firebase Analytics export, read-only via service account
- **SQLite** — local file at `~/.insightpm/insightpm.db`, stores connection profiles and saved funnels/cohorts. Single-tenant by design.
- **LLM API** (optional) — Gemini Flash or Anthropic Claude Haiku, for AI narratives. Falls back to deterministic templates when no key is configured.

---

## Backend

### Layout

```
backend/
├── app/
│   ├── main.py              ← FastAPI app, middleware, exception handlers
│   ├── auth.py              ← Optional shared-password gate
│   ├── bigquery_client.py   ← Thin wrapper over google.cloud.bigquery
│   ├── cache.py             ← In-memory TTL cache (per-key expiry)
│   ├── config.py            ← Active profile management, env var loading
│   ├── db.py                ← SQLite CRUD for profiles + saved cohorts/funnels
│   ├── logging_setup.py     ← Rotating file logger (5MB × 5 files)
│   ├── backup.py            ← CLI: `python -m app.backup backup|restore`
│   ├── models/
│   │   └── schemas.py       ← All Pydantic request/response models
│   ├── routers/             ← FastAPI HTTP route definitions
│   │   ├── auth.py
│   │   ├── connection.py
│   │   ├── events.py
│   │   ├── funnel.py
│   │   ├── retention.py
│   │   ├── insights.py
│   │   ├── nlq.py
│   │   ├── saved_funnels.py
│   │   ├── saved_cohorts.py
│   │   ├── breakdown.py
│   │   ├── sql_preview.py
│   │   ├── system.py
│   │   └── user_profile.py
│   ├── services/            ← Business logic (the interesting code)
│   │   ├── cohort_filter.py    ← Parameterized filter compiler (9 security tests)
│   │   ├── event_service.py    ← Top events, daily activity, event params
│   │   ├── funnel_service.py   ← Step-by-step funnel computation
│   │   ├── retention_service.py← D1/D7/D30 cohort retention
│   │   ├── breakdown_service.py← Property-level splits
│   │   ├── insight_engine.py   ← Rule-based insights (4 rules)
│   │   ├── anomaly_explainer.py← "Explain why" — LLM hypothesis
│   │   ├── investigator.py     ← Multi-axis Where/When/Why/What investigation
│   │   ├── user_profiler.py    ← User Behavior Profile + pattern classifier
│   │   ├── nlq_service.py      ← Natural-language Ask box
│   │   └── llm_client.py       ← Provider-agnostic Gemini/Claude wrapper
│   └── sql/                 ← SQL templates loaded by service files
│       ├── top_events.sql
│       ├── daily_activity.sql
│       ├── funnel.sql
│       ├── retention_cohort.sql
│       ├── user_journey.sql
│       ├── event_params.sql
│       └── insights/
│           ├── conversion_change.sql
│           ├── funnel_dropoff.sql
│           └── event_volume_change.sql
├── tests/                   ← 117 pytest tests
├── requirements.txt
├── Dockerfile
└── pytest.ini
```

### Request lifecycle

1. **Browser sends** `POST /api/funnel` with `{steps, date_range, cohort, ...}` and `X-InsightPM-Auth: <sha256>` header.
2. **`auth.auth_middleware`** verifies the header against the configured password digest (constant-time compare). Public paths (`/api/auth/*`, `/docs`) skip the check. If no password is configured, all requests pass.
3. **CORS middleware** validates origin.
4. **Router** (`routers/funnel.py`) parses the body into a Pydantic model — invalid input rejected with a 422.
5. **Service** (`services/funnel_service.build_funnel`) loads the SQL template from `sql/funnel.sql`, compiles the cohort filter (`cohort_filter.compile_filters`), and substitutes `{COHORT_AND}` etc.
6. **Cache check** (`cache.cached_query`) — if the same SQL+params ran within the TTL window (default 5 min), return the cached result. Otherwise:
7. **BigQuery** (`bigquery_client.run_query`) executes the parameterized query with the active profile's service account credentials.
8. **Service post-processes** raw rows into the response shape (compute conversion %, drop-off %, etc.).
9. **Response** flows back through middleware → JSON → browser.

Total cold-path latency: 800ms–4s depending on BigQuery responsiveness. Warm cache: <50ms.

### Profile management

A "profile" is a saved BigQuery connection:

```
CREATE TABLE connection_profiles (
    id              INTEGER PRIMARY KEY,
    name            TEXT UNIQUE,
    project_id      TEXT,
    dataset_id      TEXT,
    service_account_json TEXT,         -- stored plaintext, single-tenant
    is_default      INTEGER,
    created_at      TEXT
)
```

At startup, `config.initialize_active_config()`:
1. Loads the profile marked `is_default=1` if one exists.
2. Otherwise falls back to env vars (`BQ_PROJECT_ID`, `BQ_DATASET_ID`, `GCP_SERVICE_ACCOUNT_JSON`).
3. Otherwise leaves the config empty — the UI redirects to the connection form.

Switching profiles (`POST /api/profiles/{id}/use`) reloads the active config and **invalidates the cache** (so you don't see Project A's data after switching to Project B).

### Cache

`cache.cached_query` is an in-memory dict keyed by `hash(sql + params)` with per-entry TTL.

```python
key = hashlib.sha256(f"{sql}|{json.dumps(params, sort_keys=True)}".encode()).hexdigest()
```

No external Redis or memcached. Single-tenant by design. Cache evicts on TTL expiry or LRU when the dict exceeds ~500 entries.

### Logging

`logging_setup.setup_logging()` configures a rotating file handler at `~/.insightpm/logs/insightpm.log` (5MB per file, 5 file rotation). Every BigQuery query logs its SQL hash + params + execution time. Errors include stack traces.

---

## Frontend

### Layout

```
frontend/
├── src/
│   ├── App.jsx              ← Auth gate, page router (state-based, not react-router)
│   ├── main.jsx
│   ├── styles.css           ← Global styles
│   ├── api/
│   │   ├── client.js        ← Fetch wrapper, auth header injection, all endpoints
│   │   └── url_state.js     ← Encode/decode {date, cohort, funnel} → URL hash
│   └── components/
│       ├── ConnectionForm.jsx
│       ├── ProfileSwitcher.jsx
│       ├── DateRangePicker.jsx
│       ├── FreshnessBadge.jsx
│       ├── ErrorBox.jsx
│       ├── NLQBox.jsx
│       ├── InsightsPanel.jsx
│       ├── FunnelBuilder.jsx
│       ├── RetentionDashboard.jsx
│       ├── EventExplorer.jsx
│       ├── CohortBuilder.jsx
│       ├── Sparkline.jsx
│       ├── SqlPreviewModal.jsx
│       ├── UserProfiler.jsx
│       ├── LoginScreen.jsx
│       └── ShareButton.jsx
├── package.json
├── vite.config.js
└── Dockerfile
```

### State model

All component state. No Redux, no Zustand, no Context. Why:
- Single-tenant, single-page tool. Component-local state is enough.
- Cohort filter and date range live in `App.jsx`; passed down as props.
- Saved profiles list lives in `App.jsx`, fetched once after auth.
- URL hash is the source of truth for shareable view state (date + cohort + funnel).

### API client

`api/client.js` is a thin fetch wrapper that:
1. Adds `X-InsightPM-Auth: <digest>` header from sessionStorage (if set).
2. Catches 401 → clears the auth digest → throws `auth_required` (App.jsx redirects to login).
3. Parses error responses into structured `{detail, kind}` objects.

Each endpoint is a named method (`api.funnel(body)`, `api.investigateInsight(body)`, etc.). No GraphQL, no auto-generated client — just functions.

### URL state

`api/url_state.js` encodes shareable view state into the URL hash so a copied URL restores the exact view:

```javascript
encodeState({ dateRange, cohort, savedFunnelId, savedCohortId })
  → JSON.stringify → base64-urlsafe → "#s=<hash>"
```

Hash (not query string) because:
- Doesn't hit the server (no leaking cohort filters into logs)
- Doesn't trigger reloads on change
- Atomic update — one blob to encode/decode

---

## Data model

### What we query

Every analytical query reads from `{project}.{dataset}.events_*` (the Firebase Analytics BigQuery export, daily-sharded tables).

The tables we read from look like:

```sql
events_YYYYMMDD
├── event_date           STRING (YYYYMMDD)
├── event_timestamp      INT64  (microseconds)
├── event_name           STRING
├── event_params         ARRAY<STRUCT<key STRING, value STRUCT<...>>>
├── user_pseudo_id       STRING  ← stable per-device anonymous ID
├── user_id              STRING  ← only set if your app called setUserId()
├── user_properties      ARRAY<STRUCT<key STRING, value STRUCT<...>>>
├── device.category, device.operating_system, device.web_info.browser
├── geo.country, geo.region, geo.city
├── app_info.id, app_info.version
└── platform             STRING (ANDROID, IOS, WEB)
```

### Date sharding

`_TABLE_SUFFIX` filters which daily tables get scanned. We always include:

```sql
WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
```

This is critical for cost — without it BigQuery scans every day in the dataset. With it, only the requested days are scanned.

### Cohort filter compilation

`services/cohort_filter.compile_filters([{...}])` translates a list of filter dicts into a parameterized SQL fragment:

```python
input = [
    {"field": "geo.country", "field_type": "column",
     "operator": "in", "values": ["IN", "US"]},
    {"field": "first_open_time", "field_type": "user_property",
     "operator": "is_set"},
]

output:
    sql = "((geo.country IN UNNEST(@cohort_0))
            AND (EXISTS (SELECT 1 FROM UNNEST(user_properties) 
                          WHERE key='first_open_time')))"
    params = {"cohort_0": ["IN", "US"]}
```

The values are ALWAYS bound as `@params`, never string-interpolated. Fields are checked against allowlists (no `; DROP TABLE` exploits — there's no place to inject SQL). **9 dedicated security tests** verify this.

---

## AI integration

### The strict rule

The LLM never produces numbers. Every number comes from deterministic SQL.

This is enforced two ways:
1. **Architecturally** — services fetch numbers first, then build a prompt that INCLUDES the numbers, then ask the LLM to narrate. The LLM cannot invent numbers because it's told them.
2. **Prompt-wise** — every system prompt explicitly says "do not invent statistics, only cite what's given."

When the LLM hallucinates a number anyway (rare but possible), the user sees a sentence that contradicts the chart — easy to spot. We don't currently auto-detect hallucinations.

### Provider abstraction

`services/llm_client.call_llm(system, user_message, max_tokens)` tries providers in order:

1. Gemini Flash (if `GEMINI_API_KEY` set)
2. Anthropic Claude Haiku (if `ANTHROPIC_API_KEY` set)
3. Returns `None` (caller falls back to templated text)

Each provider call is wrapped in try/except. A timeout or rate-limit silently falls through to the next provider.

### Topic guardrail

Every system prompt is prepended with:

```
You are an analytics assistant. Refuse politely if the question is
unrelated to product analytics, user behavior, or the data shown.
```

This prevents misuse (people asking for help with unrelated tasks) and keeps outputs predictable.

### Where AI is used

| Feature | Service | What the LLM does |
|---|---|---|
| User Behavior Profile | `user_profiler.profile_user` | Reads journey + metrics, writes Story + Pattern + Recommendations |
| Explain Why | `anomaly_explainer.explain_insight` | Reads insight + adjacent movers, writes a hypothesis paragraph |
| Investigator | `investigator.investigate` | Reads WHERE/WHEN findings, writes hypothesis + recommended actions |
| NLQ (Ask) | `nlq_service.answer` | Routes intent (retention/cohort/funnel/etc.) and rewrites answer in prose |

Total LLM calls per "full page load": 0 unless you click an AI button. The dashboard renders deterministically from SQL only.

---

## Security

See [SECURITY.md](SECURITY.md) for the full security policy. Key points:

- **Cohort filter fields** are allowlisted; values are always bound as parameters (9 tests).
- **Service account JSON** is stored in SQLite plaintext, single-tenant by design. Don't share the SQLite file.
- **Shared password** (optional) is SHA-256 hashed on the client; the plain password never crosses the wire. Constant-time digest comparison.
- **CORS** allows only `FRONTEND_ORIGIN`. Cross-origin browsers can't call the API.
- **No cookies**. Auth digest is in sessionStorage (cleared on tab close).

---

## Tests

```bash
cd backend
python -m pytest tests/        # 117 tests, ~5 seconds
python -m pytest tests/ -v     # verbose
python -m pytest tests/test_cohort_filter.py  # one file
```

Categories:
- **Cohort filter security** (9 SQL-injection prevention tests)
- **Connection profile DB** (CRUD + uniqueness)
- **Saved funnels / saved cohorts** (CRUD + scoping per profile)
- **Auth middleware** (password verify, constant-time compare)
- **Investigator** (math + share consistency across axes)
- **Retention math** (rate computation, double-divide regression)
- **User profiler** (metrics, pattern classifier)
- **LLM client** (provider fallback, guardrail)
- **Anomaly explainer** (adjacent movers query)
- **Insight engine** (4 rules)
- **Cache** (TTL eviction)

CI / GitHub Actions setup is not yet included — see [CONTRIBUTING.md](CONTRIBUTING.md) for how to add it.

---

## Performance characteristics

| Operation | Cold | Warm cache |
|---|---|---|
| Page load (dashboard, no AI) | 1.5–3s | <300ms |
| Funnel computation (3 steps, 30 days) | 1–2s | <100ms |
| Cohort retention (30 days) | 2–4s | <100ms |
| Investigate (6 BigQuery queries + 1 LLM call) | 10–25s | 1–2s + LLM |
| User Behavior Profile (1 BigQuery query + 1 LLM call) | 3–8s | <1s + LLM |

BigQuery cost: typical session scans <100MB across all queries (well within free tier).

---

## What we deliberately don't do

See [TRADEOFFS.md](TRADEOFFS.md) for the full list with rationale. Short version:

- **Multi-tenant SaaS** — single-tenant only. Profiles per-user requires a different architecture.
- **Real-time data** — Firebase BigQuery export is daily. We don't try to fake live data.
- **A/B test integration** — out of scope; use Firebase Remote Config / GrowthBook / Statsig.
- **More LLM providers** — Gemini + Claude is enough. Adding more is straightforward (one function in `llm_client.py`) but unmaintained providers create noise.
- **Path / journey visualization** — Sankey diagrams look impressive in demos, rarely useful for decisions.
