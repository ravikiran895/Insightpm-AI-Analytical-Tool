# Tradeoffs

Honest engineering decisions made building InsightPM. What we chose, what we considered, what we deferred — and why.

If you're evaluating whether this is the right tool for your use case, or thinking about contributing, this document tells you the constraints you'll be operating inside.

---

## Single-tenant by design

**Decision:** One install per person / team. No user accounts, no permissions, no per-user data isolation.

**What we considered:** Multi-tenant SaaS where each user gets their own account, profiles are scoped per user, billing is per-seat.

**Why we chose single-tenant:**
- The whole point is "self-hosted, your data" — adding multi-tenancy would mean either centralizing data (defeats the point) or building federation (massive engineering).
- Personal/small-team analytics doesn't need user accounts. Trust model is "everyone with access to the box can see everything."
- Multi-tenant adds significant complexity: auth, permissions, isolation testing, data leakage prevention. Months of work for a feature most users don't need.

**Consequence:** This will never be SaaS. If you want SaaS-style analytics, use Mixpanel/Amplitude. We're the alternative for people who don't want SaaS.

---

## SQL is the source of truth. AI is the narrator.

**Decision:** The LLM never produces numbers. Every metric on every chart comes from deterministic SQL. The AI's only job is pattern-recognition and narrative.

**What we considered:** Letting the LLM compute summaries directly from raw data (less SQL to write, more flexible).

**Why we chose strict separation:**
- LLMs hallucinate numbers. A wrong metric in a PM tool destroys trust permanently.
- SQL is auditable. "View SQL" button on every chart shows the exact query that produced the number. AI computations would not be auditable.
- The architectural promise ("AI doesn't do the math") is enforceable only if the code is structured this way.

**Consequence:** Adding a new metric requires writing SQL. The LLM can't shortcut around it. This is intentional friction.

---

## In-memory cache, no Redis

**Decision:** TTL cache lives in Python process memory. Restart the server, cache is gone.

**What we considered:** Redis/memcached for shared cache across instances.

**Why in-memory:**
- Single-tenant tool. One process per install. Shared cache is meaningless.
- Adding Redis means an extra service to install, configure, monitor, and maintain.
- BigQuery's own server-side cache catches most repeat queries (free). Adding another layer is marginal.

**Consequence:** Restart = cold cache. Doesn't matter at our scale.

---

## SQLite, not Postgres

**Decision:** Saved profiles, funnels, cohorts live in a single SQLite file at `~/.insightpm/insightpm.db`.

**What we considered:** Postgres or MySQL for "real" relational storage.

**Why SQLite:**
- Single-tenant. One process. SQLite is plenty.
- No external service to install. Just a file.
- Backup is trivial: copy the file.
- Migrations are easier: just version your schema and apply at startup.

**Consequence:** No concurrent writers from multiple processes. We don't need that.

---

## No ORM

**Decision:** Raw `sqlite3` module with hand-written SQL. No SQLAlchemy, no Tortoise, no Prisma.

**What we considered:** SQLAlchemy for type-safety and migrations.

**Why raw SQL:**
- 3 tables. ~20 functions. ORM is overkill.
- Faster to read for someone new to the codebase.
- No magic. What you see is what runs.

**Consequence:** Schema migrations are manual (we just `CREATE TABLE IF NOT EXISTS` and additive ALTERs). Fine for the project's scale.

---

## React with no global state library

**Decision:** Component-local state and prop drilling. No Redux, no Zustand, no Context for anything bigger than themeing.

**What we considered:** Redux Toolkit, Zustand, React Query, TanStack.

**Why none:**
- App has ~15 components. State complexity doesn't justify a global store.
- React Query would be nice for cache invalidation, but our 5-min server-side cache makes it less necessary.
- Adding a state library is a permanent commitment — once it's in, every component touches it.

**Consequence:** When the app grows past ~30 components, this will start hurting. We're not there.

---

## No react-router

**Decision:** Page routing is `useState('dashboard' | 'profile' | 'investigator')` in App.jsx.

**What we considered:** React Router for proper URL-based navigation.

**Why state-based:**
- The app has 3-4 "pages." Trivial.
- Deep linking matters mostly for sharing — we handle that via URL hash (`#s=<encoded state>`), not paths.
- React Router would add a dependency for one feature we mostly don't need.

**Consequence:** Browser back button doesn't navigate between pages. Acceptable for an internal tool.

---

## No Tailwind

**Decision:** Plain CSS file with custom properties (CSS variables). No utility framework.

**What we considered:** Tailwind, styled-components, Emotion, CSS Modules.

**Why plain CSS:**
- Tailwind requires a build step + config + IDE setup. CSS just works.
- 600 lines of CSS is easier to grep than 10,000 utility classes scattered through JSX.
- Easier for contributors who don't know Tailwind.

**Consequence:** Slightly more verbose component JSX. We gain readability and zero build config.

---

## Vite, not Next.js / Remix

**Decision:** Vite dev server + static build. No SSR, no framework.

**What we considered:** Next.js for SSR + API routes (we'd not need a separate FastAPI server).

**Why Vite:**
- The tool is private/internal. SSR doesn't help us.
- Keeping backend (Python/FastAPI) and frontend (JS/React) separate is clearer.
- Vite is fast.

**Consequence:** Two processes to run in dev (`uvicorn` + `npm run dev`). Acceptable.

---

## Two AI providers, not more

**Decision:** Gemini Flash and Anthropic Claude Haiku are supported. OpenAI, Mistral, others are not.

**What we considered:** Supporting every LLM provider via litellm or LangChain.

**Why two:**
- Each provider needs maintenance (SDK upgrades, retry logic, prompt tuning).
- Two providers gives users a fallback. More than two adds noise.
- Adding a third (OpenAI) is straightforward: ~30 lines in `llm_client.py`. We just haven't.

**Consequence:** If you only have an OpenAI key, you'd need to either add the provider yourself (PR welcome) or use the deterministic templates.

---

## Daily data, not real-time

**Decision:** We read Firebase's BigQuery export, which runs once per day. We don't try to query the intraday table or simulate real-time.

**What we considered:** Querying `events_intraday_YYYYMMDD` for today's partial data, or implementing real-time event ingestion.

**Why daily:**
- Real-time analytics is a different product. Building it requires ingestion infrastructure (Kafka/Pub-Sub), stream processing, hot storage.
- PMs make weekly/biweekly decisions, not minute-by-minute. Daily is plenty.
- Adding "today" data would require special-casing the intraday table everywhere.

**Consequence:** "Today" is always missing. PMs adjust by looking at "yesterday and earlier" — which is what they were doing anyway.

---

## No path / journey visualization

**Decision:** No Sankey diagrams, no flow charts, no user journey maps.

**What we considered:** Sankey via D3 (Mixpanel/Amplitude both ship these).

**Why not:**
- Sankey diagrams look impressive in product demos. PMs rarely use them for decisions.
- The data shape (events with arbitrary properties) doesn't naturally produce clean flows.
- We'd rather invest the time in features PMs actually use.

**Consequence:** People who specifically want path analysis won't find it here. Funnel + cohort breakdown covers 90% of their need.

---

## No A/B test integration

**Decision:** This tool doesn't read from your A/B testing platform.

**What we considered:** Reading Firebase Remote Config experiment data.

**Why not:**
- Out of scope. The tool's job is "understand who your users are and what they do," not "evaluate experiment results."
- A/B testing requires statistical significance machinery, p-values, sample-size calculators — a different product entirely.

**Consequence:** Use GrowthBook / Statsig / Optimizely / native Firebase A/B testing for experiments. Use this for behavioral analysis.

---

## No mobile-responsive layout (yet)

**Decision:** The UI is desktop-only. Phone/tablet views are broken.

**What we considered:** Designing mobile-first.

**Why deferred:**
- PMs do real analytics work on laptops. Mobile is mostly for "did the dashboard alert me to something?" — a Slack digest serves that better.
- Building mobile-responsive doubles the design surface.

**Consequence:** v0.10 was planned to include mobile, but priorities shifted. Listed in roadmap.

---

## Shared password, not real auth

**Decision:** Optional `INSIGHTPM_PASSWORD` env var enables a single shared password. No user accounts, no SSO, no roles.

**What we considered:** OAuth, JWT sessions, role-based access control.

**Why shared password:**
- Single-tenant. Team model is "everyone with the password can see everything."
- Real auth is a months-long project. Shared password is 50 lines.
- The threat model is "accidental discovery" (someone scanning the LAN finds your localhost:5173). Not "adversarial multi-user."

**Consequence:** If you need real auth, this isn't the tool. For small teams who trust each other, it's plenty.

---

## What we shipped that we considered cutting

A few things made it in despite low ROI debates:

### "View SQL" button on every chart

**Why we shipped it anyway:** PMs trust opaque analytics tools roughly 0%. Showing the exact SQL builds trust. It's also a debugging tool when numbers look wrong.

### Saved cohorts and saved funnels

**Why we shipped it anyway:** Rebuilding the same filter every time is annoying. Saving is one extra click.

### Multi-project support (profiles)

**Why we shipped it anyway:** People who build multiple apps want to analyze them with one install. Two database tables, one switcher widget. Worth it.

### URL state sharing

**Why we shipped it anyway:** PMs share findings on Slack/email. A link that restores the exact view they're seeing turns "look at this chart" into a meaningful share. Two-day build.

---

## Roadmap (what we'd build next)

In rough priority order, none currently committed:

1. **Email/property search for users** — currently users can only be looked up by `user_pseudo_id`. Many real workflows want to search by email or custom user properties.
2. **Auto-discovered behavior patterns** — nightly job that surfaces "unexpected user clusters" without the user defining them in advance.
3. **Slack/email weekly digest** — push the top 3 insights to Slack every Monday morning.
4. **Mobile-responsive UI** — for at-a-glance checks on phone.
5. **Onboarding wizard** — first-run flow that walks new users through service-account setup with copy-paste commands.
6. **GitHub Actions CI** — automatic test runs on PRs.

If any of these matter to you, open an issue or PR. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Last word

Every "we didn't build X" decision above is reversible. Nothing in the architecture forecloses these features — we just haven't done them. If your use case needs one, contributions are very welcome.

The only truly load-bearing decision is the single-tenant model. Multi-tenancy would require rewriting profile management, auth, caching, and probably 30% of the backend. We won't be doing that.
