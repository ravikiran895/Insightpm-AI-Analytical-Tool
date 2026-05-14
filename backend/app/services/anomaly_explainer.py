"""
Anomaly explanation service.

Takes a fired insight + relevant context, asks Claude Haiku to write a
hypothesis about what might explain the change. Returns a 2-3 sentence
explanation with explicit "this is a hypothesis" framing.

Design constraints (the things that prevent hallucination):

1. We give the LLM *only the numbers we already computed*. It never sees raw
   user data, never makes up percentages, never sums anything. We tell it
   exactly what each number means.

2. The output is framed as a hypothesis. Prompt explicitly forbids stating
   conclusions as fact. We post-process to add "Hypothesis:" prefix if the
   model didn't.

3. Context is bounded: we send at most ~30 data points (top movers, segment
   counts). Bounded input -> bounded output -> bounded cost. Each call is
   ~1k tokens in, ~150 out -- around $0.001.

4. Falls back to a templated explanation if no API key. We never block on the
   LLM, just gracefully degrade.

5. Result is cached per (insight_id, date_range) for 1 hour. Clicking
   Explain twice in a row doesn't re-bill.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, timedelta
from typing import Any, Optional

from ..bigquery_client import run_query
from ..cache import cached_query
from ..config import get_active_config
from . import event_service
from .cohort_filter import compile_filters
from .llm_client import call_llm

log = logging.getLogger("insightpm.anomaly")


_SYSTEM_PROMPT = """You are a product analyst helping a PM understand a metric change.

You will be given:
- An insight that fired (a metric change with exact numbers)
- Surrounding context: other metrics that moved, segment shifts, etc.

Write a 2-3 sentence HYPOTHESIS about what might explain the change.

Strict rules:
- Start your response with "Hypothesis: " (literally those characters).
- Reference SPECIFIC numbers from the context. Never invent numbers.
- Use hedging language: "may be related to", "could be driven by", "appears to coincide with".
- Never state a conclusion as fact. You don't have causal evidence, only correlations.
- If the context is insufficient to form a hypothesis, say "Hypothesis: insufficient context to explain this change. Suggested: check X and Y."
- Be specific. Vague hypotheses ("user behavior changed") are useless.
- Keep it to 2-3 sentences. No bullet lists. No headers.
"""


def _gather_context(insight: dict, date_range: tuple[str, str]) -> dict[str, Any]:
    """Pull surrounding metrics that might illuminate the insight.

    Strategy:
    - For 'conversion' / 'funnel' insights: look at top-event volume changes
      in the same window (something might've spiked/dropped that drove this).
    - For 'volume' insights: that's already a volume change, return it.
    - For 'retention' insights: pull recent retention correlation top-3.

    All queries respect the active connection. We use the existing cache so
    if the dashboard already loaded these, they're free."""
    cfg = get_active_config()
    start, end = date_range
    context: dict[str, Any] = {
        "insight_kind": insight.get("kind"),
        "insight_metric": insight.get("metric", {}),
        "date_range": {"start": start, "end": end},
    }

    # Always include top events of the window for grounding.
    try:
        top = event_service.top_events(start, end, limit=10)
        context["top_events"] = [
            {"event": r["event_name"], "users": r["unique_users"]}
            for r in top
        ]
    except Exception as e:  # noqa: BLE001
        log.warning(f"top_events context fetch failed: {e}")
        context["top_events"] = []

    # For conversion / funnel kinds, also pull WoW event volume changes.
    if insight.get("kind") in ("conversion", "funnel"):
        try:
            this_end_d = date.fromisoformat(_iso(end))
            this_start_d = date.fromisoformat(_iso(start))
            length = (this_end_d - this_start_d).days + 1
            prev_end_d = this_start_d - timedelta(days=1)
            prev_start_d = prev_end_d - timedelta(days=length - 1)
            sql = f"""
            WITH this_period AS (
              SELECT event_name, COUNT(DISTINCT user_pseudo_id) AS users
              FROM {cfg.events_table}
              WHERE _TABLE_SUFFIX BETWEEN @ts AND @te
              GROUP BY event_name
            ),
            prev_period AS (
              SELECT event_name, COUNT(DISTINCT user_pseudo_id) AS users
              FROM {cfg.events_table}
              WHERE _TABLE_SUFFIX BETWEEN @ps AND @pe
              GROUP BY event_name
            )
            SELECT
              COALESCE(t.event_name, p.event_name) AS event_name,
              IFNULL(t.users, 0) AS this_users,
              IFNULL(p.users, 0) AS prev_users,
              SAFE_DIVIDE(IFNULL(t.users, 0) - IFNULL(p.users, 0), NULLIF(p.users, 0)) AS pct_change
            FROM this_period t
            FULL OUTER JOIN prev_period p USING (event_name)
            WHERE IFNULL(p.users, 0) >= 30
            ORDER BY ABS(IFNULL(pct_change, 0)) DESC
            LIMIT 8
            """
            rows = run_query(sql, {
                "ts": end[:8] if len(end) == 8 else _yyyymmdd_str(this_start_d.isoformat()),
                "te": end,
                "ps": _yyyymmdd_str(prev_start_d.isoformat()),
                "pe": _yyyymmdd_str(prev_end_d.isoformat()),
            })
            context["adjacent_movers"] = [
                {
                    "event": r["event_name"],
                    "this": r["this_users"],
                    "prev": r["prev_users"],
                    "pct_change": float(r["pct_change"] or 0),
                }
                for r in rows
            ]
        except Exception as e:  # noqa: BLE001
            log.warning(f"adjacent movers fetch failed: {e}")
            context["adjacent_movers"] = []
    else:
        context["adjacent_movers"] = []

    return context


def _iso(yyyymmdd: str) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD."""
    if len(yyyymmdd) == 8 and yyyymmdd.isdigit():
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"
    return yyyymmdd


def _yyyymmdd_str(iso: str) -> str:
    return iso.replace("-", "")


def _build_user_prompt(insight: dict, context: dict) -> str:
    lines = [
        "An insight fired:",
        f"  Title: {insight.get('title', '<no title>')}",
        f"  Detail: {insight.get('detail', '<no detail>')}",
        f"  Kind: {insight.get('kind')}",
        f"  Severity: {insight.get('severity', 0):.2f}",
        f"  Metric: {json.dumps(insight.get('metric', {}), default=str)}",
        "",
        f"Date range analyzed: {context['date_range']['start']} to {context['date_range']['end']}",
        "",
    ]
    if context.get("top_events"):
        lines.append("Top events (this period, by unique users):")
        for e in context["top_events"][:8]:
            lines.append(f"  - {e['event']}: {e['users']} users")
        lines.append("")
    if context.get("adjacent_movers"):
        lines.append("Other events with biggest WoW change (this vs previous period):")
        for m in context["adjacent_movers"]:
            pct = m["pct_change"]
            arrow = "↑" if pct > 0 else "↓"
            lines.append(
                f"  - {m['event']}: {m['this']} this period, {m['prev']} previous, {arrow} {abs(pct)*100:.1f}%"
            )
        lines.append("")
    lines.append("Write your hypothesis now. Remember: 2-3 sentences, start with 'Hypothesis: ', cite specific numbers from the context above.")
    return "\n".join(lines)


def _explain_with_llm(insight: dict, context: dict) -> Optional[tuple[str, str]]:
    """Returns (explanation text, provider_name) or None on failure."""
    result = call_llm(
        system=_SYSTEM_PROMPT,
        user_message=_build_user_prompt(insight, context),
        max_tokens=300,
    )
    if result is None:
        return None
    text, provider = result
    # Defense in depth: ensure the "Hypothesis:" prefix.
    if not text.lower().startswith("hypothesis"):
        text = "Hypothesis: " + text
    return (text, provider)


def _explain_with_template(insight: dict, context: dict) -> str:
    """Deterministic fallback when no LLM available. Useful, but not as good
    as the LLM version. Pattern-matches on insight kind."""
    kind = insight.get("kind")
    movers = context.get("adjacent_movers") or []
    top_movers = [m for m in movers if abs(m["pct_change"]) >= 0.20][:3]

    parts = ["Hypothesis: "]
    if kind == "conversion":
        if top_movers:
            mover_str = ", ".join(
                f"{m['event']} {'+' if m['pct_change'] > 0 else '−'}{abs(m['pct_change'])*100:.0f}%"
                for m in top_movers
            )
            parts.append(
                f"the conversion change may be related to other events moving in the same window ({mover_str}). "
                f"Worth checking whether traffic mix or upstream funnel volume shifted."
            )
        else:
            parts.append(
                "no strong adjacent metric movement detected to explain this change. "
                "Consider checking by cohort segment (platform, country, app version) for a localized cause."
            )
    elif kind == "funnel":
        ev = insight.get("metric", {}).get("event", "this step")
        parts.append(
            f"the drop at {ev} could indicate a UX friction point or a change in upstream user mix. "
            f"Try the 'Break down by' control with platform or app version to localize the cause."
        )
    elif kind == "retention":
        parts.append(
            "users who do this event early may be self-selecting into a more engaged segment. "
            "Correlation does not imply causation here -- consider an A/B test before betting on this lever."
        )
    elif kind == "volume":
        parts.append(
            "this volume shift may reflect a marketing campaign, app release, or seasonal effect. "
            "Cross-reference with your release notes or ad spend for the same window."
        )
    else:
        parts.append("insufficient signal to form a hypothesis. Try widening the date range or examining segment breakdowns.")

    return "".join(parts)


def explain_insight(insight: dict, date_range: tuple[str, str]) -> dict[str, Any]:
    """Main entry: pull context, ask LLM (or fall back), return result.

    Caching: result is cached at the in-process layer for 1 hour, keyed on
    (insight_id, date_range, classifier_kind). So clicking Explain twice in
    a row hits the cache."""
    insight_id = insight.get("id", "unknown")
    cache_key = hashlib.sha256(
        json.dumps([insight_id, date_range], sort_keys=True).encode()
    ).hexdigest()

    # Use cached_query as a generic cache (the runner just builds the explanation).
    def _runner(_sql: str, _params: dict | None) -> list[dict]:
        ctx = _gather_context(insight, date_range)
        llm_result = _explain_with_llm(insight, ctx)
        if llm_result:
            text, provider = llm_result
            return [{"explanation": text, "source": provider, "context": ctx}]
        fallback = _explain_with_template(insight, ctx)
        return [{"explanation": fallback, "source": "template", "context": ctx}]

    rows = cached_query(
        sql=f"-- explain:{cache_key}",   # opaque key for the cache layer
        params=None,
        runner=_runner,
        ttl_seconds=3600,
    )
    return rows[0]
