# Changelog

## v0.9.2 — Math correctness audit + bug fixes

A full audit of every analytical pathway in the codebase. Three real bugs
fixed (one critical), two minor wording improvements, six modules confirmed
correct. Posting publicly without this audit would have damaged credibility.

### Bug 1 (critical, fixed): Retention double-divide

**Symptom:** D1/D7/D30 retention percentages displayed ~1000× too small.
A real 18% retention rate would appear as roughly 0.018%.

**Root cause:** The retention service computed
`d1_avg = sum(d1_users) / total_users` -- which is already a rate (e.g. 0.18).
But three consumers (frontend `RetentionDashboard`, `nlq_service`,
`breakdown_service`) all then divided by `total_users` again before
multiplying by 100. The bug had been latent since v0.4 because nobody
looked carefully at the displayed numbers.

**Fix:**
- Backend now returns `dN_avg` as rates (0-1), `dN_retained` as counts,
  and `total_users` as the cohort denominator. Field semantics are
  documented at the call site.
- All four consumers updated to use `dN_avg` directly without re-dividing.
- 3 regression tests added (`test_retention_math.py`).

### Bug 2 (critical, fixed in v0.9.1): Investigator WHERE inconsistent counts

**Symptom:** WHERE section showed inconsistent user counts across
dimensions (e.g. country: 45 users, platform: 99 users) all labeled "100%".

**Root cause:** Each axis was independently counting users per top value
in the period, with share computed against the sum of that axis's top-5
values. So "100% of country=Russia" really meant "100% of the top-5
countries that met a >=30 user threshold." Different denominator per axis.

**Fix:**
- WHERE query now counts only users who fired the **target event** (the
  metric that actually changed).
- Single shared denominator (`total_affected_users`) used across all axes.
- Removed `>=30` filter that was hiding small segments.
- 2 regression tests added (`TestShareConsistency`).

### Bug 3 (moderate, fixed): User Profile metrics truncated by journey limit

**Symptom:** A user's metrics (event count, session count, engagement
minutes, lifespan) were derived from their journey list -- which is capped
at 200 events for display. A user with 500 actual events would show 200
events and undercount engagement minutes.

**Root cause:** `compute_metrics()` operated on the truncated journey
returned for display purposes. The truncation was correct for display
(don't bloat the response) but incorrect for metric calculation.

**Fix:**
- New `fetch_aggregate_metrics()` query computes accurate totals across
  the full window via a separate small SQL query.
- `profile_user()` now overlays the journey-derived metrics with the
  accurate aggregates before classifying the pattern.
- Lifespan recomputed from accurate first/last seen.
- The aggregate query also returns proper distinct session count via
  `ga_session_id` event_param (more accurate than counting unique
  `session_id` strings from a truncated journey).

### Wording fix: Retention correlation lift

**Before:** `'Users who do "X" on day 1 retain 6.0% better at D7'` --
ambiguous (could read as 6 percentage points or +6% relative).

**After:** `'Users who do "X" on day 1 retain 6.0pp better at D7'`. The
detail line now explicitly says `'Lift: +6.0 percentage points'`.

### Modules audited and confirmed correct (no changes)

- **funnel_service.build_funnel** -- drop-off and conversion math correct
- **insight_engine.rule_conversion_change** -- rate comparison logic correct
- **insight_engine.rule_largest_funnel_dropoff** -- uses funnel output correctly
- **insight_engine.rule_event_volume_change** -- pct_change math verified
- **insight_engine._periods_from_range** -- date arithmetic verified
- **event_service** -- pure SQL counts, no derived math
- **anomaly_explainer** adjacent-movers query -- math correct
- **investigator WHEN** inflection detection -- 25% divergence threshold
  correct, edge-cases bounded by `max(baseline, 1)` to avoid noise

### Tests

**117 passing in ~5s.** New since v0.9.0:
- 3 retention math regression tests
- 2 investigator share-consistency tests (added in v0.9.1)

Total test breakdown:
- 9 cohort filter security tests (SQL injection prevention)
- 14 connection profile DB tests
- 7 saved funnel tests
- 7 saved cohort tests
- 6 auth tests
- 11 investigator tests (including 2 share-consistency)
- 3 retention math tests
- 9 user profiler tests
- 16 LLM client tests
- 13 anomaly explainer tests
- 11 insight engine tests
- 11 cache tests

### Upgrade notes

**No new dependencies. No new env vars.** Just unzip over the existing
folder and restart uvicorn.

If you compare retention numbers before vs after the upgrade, they will
look ~1000× larger after upgrade (because they're now correct). This is
not a regression -- the previous numbers were wrong.

### What this audit confirmed about the architecture

The "AI never produces numbers" claim now genuinely holds. Every metric
shown in the UI traces back to deterministic SQL that has been examined
for correctness. The LLM only narrates over verified numbers.

Two of the three bugs found were in display-layer code (retention
double-divide) and one was in query-construction (investigator WHERE).
None of them were in the LLM prompts or AI synthesis -- which is what
the architecture promised.

### Pending

USP 3 (auto-discovered patterns), Slack digest, mobile responsive,
onboarding wizard, requirements.txt version pinning to prevent the
recurring anthropic/httpx version conflict.
