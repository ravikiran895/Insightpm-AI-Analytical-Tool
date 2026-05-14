"""
Where/When/Why Investigator (USP 2).

Takes a fired insight and answers four questions in parallel:

  WHERE: which user segments is this concentrated in?
         (top splits by country, platform, app version)
  WHEN:  when did this start? Is it gradual or sudden?
         (day-by-day metric trace over the period + before)
  WHY:   what's the most plausible cause?
         (LLM hypothesis given the where/when context)
  WHAT:  what should the PM do about it?
         (LLM-generated recommended action with rough impact)

Design constraints:
- Bounded query count: max ~6 queries per investigation. We're not running
  N**2 dimensional analyses; we pick the 3 axes most likely to illuminate.
- Bounded LLM cost: one LLM call. Inputs are the structured findings from
  the queries above. Output is a single hypothesis + recommendation.
- Hard cache: 30 minutes per (insight_id, date_range). Expensive to compute,
  not interesting to recompute on every click.
- Deterministic fallback: if the LLM is unavailable, we still return the
  WHERE/WHEN/WHAT data and a templated WHY.

Why this matters as a USP:
- Existing analytics tools show you 12 charts. This gives you 1 decision.
- The synthesis step (LLM) requires per-investigation reasoning that doesn't
  fit SaaS unit economics.
- The WHEN axis especially is hard to do well -- requires the system to
  pick the right time window automatically based on the insight kind.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from ..bigquery_client import run_query
from ..cache import cached_query
from ..config import get_active_config
from .cohort_filter import compile_filters
from .llm_client import call_llm

log = logging.getLogger("insightpm.investigator")


# Axes we try to dimensionalize on. Order matters: we run the cheap/likely
# axes first and stop early if one is overwhelmingly explanatory.
_AXES = [
    {"field": "geo.country", "field_type": "column", "label": "country"},
    {"field": "platform", "field_type": "column", "label": "platform"},
    {"field": "app_info.version", "field_type": "column", "label": "app version"},
    {"field": "device.category", "field_type": "column", "label": "device category"},
]


def _iso_to_yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _yyyymmdd_to_date(s: str) -> date:
    return date.fromisoformat(f"{s[:4]}-{s[4:6]}-{s[6:8]}")


# ============================================================================
# WHERE -- which segments concentrate the change
# ============================================================================

def _investigate_where(
    insight: dict,
    start: str,
    end: str,
    base_cohort: Optional[list[dict]],
) -> dict[str, Any]:
    """For each axis, find the top values driving the metric in this period.

    Counts ONLY users who fired the target event (the metric that changed),
    so share percentages are 'X% of affected users' -- consistent across all
    axes. Bug fix from earlier version: previously counted all-users which
    made dimension counts inconsistent with each other."""
    cfg = get_active_config()
    compiled = compile_filters(base_cohort)
    cohort_and = f"AND {compiled.sql}" if compiled.sql else ""

    insight_kind = insight.get("kind")

    # Pick a target event based on insight kind. Fall back gracefully.
    target_event = (insight.get("metric") or {}).get("event") \
                  or (insight.get("metric") or {}).get("end_event") \
                  or "session_start"

    # Step 1: compute total affected users (users who fired the target event in the period).
    # This is the denominator for ALL axis share calculations -- ensures consistency.
    total_sql = f"""
    SELECT COUNT(DISTINCT user_pseudo_id) AS total_users
    FROM {cfg.events_table}
    WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
      AND event_name = @target_event
      {cohort_and}
    """
    total_params = {
        "start_date": start, "end_date": end,
        "target_event": target_event,
        **compiled.params,
    }
    try:
        total_rows = run_query(total_sql, total_params, cache_ttl_seconds=900)
        total_affected = int(total_rows[0]["total_users"]) if total_rows else 0
    except Exception as e:  # noqa: BLE001
        log.warning(f"WHERE total-affected query failed: {e}")
        total_affected = 0

    if total_affected == 0:
        return {
            "axes": {axis["label"]: [] for axis in _AXES},
            "insight_kind": insight_kind,
            "total_affected_users": 0,
        }

    out: dict[str, list[dict]] = {}

    # Step 2: per axis, count distinct users WHO FIRED THE TARGET EVENT, grouped by value.
    # Now share = users_in_value / total_affected, consistent across all axes.
    for axis in _AXES:
        try:
            sql = f"""
            SELECT
              {axis['field']} AS value,
              COUNT(DISTINCT user_pseudo_id) AS users
            FROM {cfg.events_table}
            WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
              AND event_name = @target_event
              {cohort_and}
            GROUP BY value
            HAVING value IS NOT NULL AND value != ''
            ORDER BY users DESC
            LIMIT 5
            """
            params = {
                "start_date": start, "end_date": end,
                "target_event": target_event,
                **compiled.params,
            }
            rows = run_query(sql, params, cache_ttl_seconds=900)

            # Share = % of total affected users. Now consistent across axes.
            for r in rows:
                r["share"] = r["users"] / total_affected
                # Backwards-compat alias used by some narrative builders
                r["target_count"] = r["users"]
            out[axis["label"]] = rows
        except Exception as e:  # noqa: BLE001
            log.warning(f"WHERE axis {axis['label']} failed: {e}")
            out[axis["label"]] = []

    return {
        "axes": out,
        "insight_kind": insight_kind,
        "total_affected_users": total_affected,
    }


def _is_concentrated(rows: list[dict], threshold: float = 0.6) -> Optional[dict]:
    """If the top value accounts for >threshold of users, return it.
    This is what makes WHERE actionable: 'India is 73% of the affected users'
    is more useful than 'here are 5 segments.'"""
    if not rows:
        return None
    top = rows[0]
    if top.get("share", 0) >= threshold:
        return top
    return None


# ============================================================================
# WHEN -- timeline of the metric, day-by-day
# ============================================================================

def _investigate_when(
    insight: dict,
    start: str,
    end: str,
    base_cohort: Optional[list[dict]],
) -> dict[str, Any]:
    """Day-by-day count for the target event, going back 2x the analysis
    window so we see baseline + change."""
    cfg = get_active_config()

    # Extend backwards: if the insight period is 30 days, look at the 30 days
    # before + the 30 days during.
    end_d = _yyyymmdd_to_date(end)
    start_d = _yyyymmdd_to_date(start)
    period_len = (end_d - start_d).days + 1
    extended_start_d = start_d - timedelta(days=period_len)
    extended_start = _iso_to_yyyymmdd(extended_start_d)

    compiled = compile_filters(base_cohort)
    cohort_and = f"AND {compiled.sql}" if compiled.sql else ""

    target_event = (insight.get("metric") or {}).get("event") \
                  or (insight.get("metric") or {}).get("end_event") \
                  or "session_start"

    sql = f"""
    SELECT
      PARSE_DATE('%Y%m%d', _TABLE_SUFFIX) AS date,
      COUNT(DISTINCT user_pseudo_id) AS dau,
      COUNTIF(event_name = @target_event) AS target_count
    FROM {cfg.events_table}
    WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
      {cohort_and}
    GROUP BY date
    ORDER BY date
    """

    params = {
        "start_date": extended_start,
        "end_date": end,
        "target_event": target_event,
        **compiled.params,
    }

    rows = run_query(sql, params, cache_ttl_seconds=900)
    timeline = [
        {
            "date": r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"]),
            "dau": int(r["dau"]),
            "target_count": int(r["target_count"]),
        }
        for r in rows
    ]

    # Find the day where target_count diverges from baseline. Algorithm:
    # split timeline at the analysis-period boundary, compute mean of the
    # before-period, find the first day in the after-period where target_count
    # diverges by >25%.
    boundary = start
    before = [r for r in timeline if r["date"].replace("-", "") < boundary]
    after = [r for r in timeline if r["date"].replace("-", "") >= boundary]

    change_started_on = None
    if before and after:
        baseline = sum(r["target_count"] for r in before) / len(before) or 1
        for r in after:
            if abs(r["target_count"] - baseline) / max(baseline, 1) >= 0.25:
                change_started_on = r["date"]
                break

    return {
        "timeline": timeline,
        "baseline_period": {"start": extended_start, "end": start},
        "analysis_period": {"start": start, "end": end},
        "change_started_on": change_started_on,
    }


# ============================================================================
# WHY + WHAT -- LLM synthesis
# ============================================================================

_INVESTIGATOR_SYSTEM_PROMPT = """You are a senior product analyst writing a 1-page investigation report for a PM.

You will be given a fired insight + structured findings from WHERE (segment concentration) and WHEN (timeline) analysis.

Write your response in this EXACT structure (markdown):

**Why (hypothesis)**: 2-3 sentences proposing the most likely cause, citing specific findings from the WHERE and WHEN data. Use hedging language: "appears to be", "may be driven by", "coincides with". Never state conclusions as fact.

**What to do**: 1-2 specific, actionable recommendations. Be concrete. "Investigate X by doing Y" beats "look into this further."

Strict rules:
- Reference SPECIFIC numbers and segments from the data. Never invent.
- If the data is too sparse or noisy to form a confident hypothesis, say so directly. "Hypothesis: insufficient signal -- recommend [specific check]."
- Stay under 150 words total.
- No bullet lists inside paragraphs. No emoji.
"""


def _build_llm_prompt(insight: dict, where: dict, when: dict) -> str:
    total_affected = where.get("total_affected_users", 0)
    lines = [
        "INSIGHT:",
        f"  Title: {insight.get('title', '?')}",
        f"  Detail: {insight.get('detail', '?')}",
        f"  Kind: {insight.get('kind')}",
        f"  Severity: {insight.get('severity', 0):.2f}",
        "",
        f"WHERE FINDINGS (segment concentration -- {total_affected} total affected users):",
    ]

    for axis_label, rows in where["axes"].items():
        if not rows:
            continue
        lines.append(f"  By {axis_label}:")
        for r in rows[:3]:
            share_pct = (r.get("share", 0) * 100)
            lines.append(f"    - {r['value']}: {r['users']} users ({share_pct:.1f}%)")
        concentrated = _is_concentrated(rows)
        if concentrated:
            lines.append(
                f"    [Concentrated: {concentrated['value']} accounts for "
                f"{concentrated['share']*100:.0f}% of affected users]"
            )

    lines.append("")
    lines.append("WHEN FINDINGS (timeline):")
    if when.get("change_started_on"):
        lines.append(f"  Change appeared to begin: {when['change_started_on']}")
    else:
        lines.append("  No clear inflection point detected -- gradual or noisy.")

    # Sample the timeline if long (LLM doesn't need every day)
    timeline = when["timeline"]
    if len(timeline) > 14:
        # Show first 7 + last 7
        sampled = timeline[:7] + timeline[-7:]
    else:
        sampled = timeline
    lines.append(f"  Day-by-day target_count (sampled, {len(sampled)} of {len(timeline)} days):")
    for r in sampled:
        lines.append(f"    {r['date']}: {r['target_count']} (DAU {r['dau']})")

    lines.append("")
    lines.append("Now write the Why + What sections per the structure.")
    return "\n".join(lines)


def _llm_synthesize(insight: dict, where: dict, when: dict) -> Optional[tuple[str, str]]:
    """Returns (markdown text, provider name) or None on failure."""
    prompt = _build_llm_prompt(insight, where, when)
    result = call_llm(
        system=_INVESTIGATOR_SYSTEM_PROMPT,
        user_message=prompt,
        max_tokens=300,
    )
    if result is None:
        return None
    return result  # (text, provider)


def _template_synthesize(insight: dict, where: dict, when: dict) -> str:
    """Deterministic fallback. Cites real numbers from where/when, no LLM."""
    parts = []

    # Why
    parts.append("**Why (hypothesis)**: ")
    concentrated_axes = []
    for axis_label, rows in where["axes"].items():
        c = _is_concentrated(rows)
        if c:
            concentrated_axes.append(f"{c['value']} ({axis_label}, {c['share']*100:.0f}% of affected)")

    if concentrated_axes:
        parts.append(
            f"this change appears concentrated in "
            f"{' and '.join(concentrated_axes)}. "
        )
    else:
        parts.append(
            "no single segment dominates the affected population, "
            "suggesting a broad-base change rather than a localized one. "
        )

    if when.get("change_started_on"):
        parts.append(f"The shift appears to have begun on {when['change_started_on']}.")

    parts.append("\n\n**What to do**: ")
    if concentrated_axes:
        parts.append(
            f"Run a follow-up funnel filtered to the concentrated segment "
            f"({concentrated_axes[0].split(' (')[0]}) to confirm. "
            f"Cross-check whether a release, content change, or campaign coincided "
            f"with the inflection point. "
        )
    else:
        parts.append(
            "Use the cohort filter to narrow on country, platform, and app version "
            "individually. If still no segment stands out, the cause is likely "
            "a global product or marketing change."
        )

    return "".join(parts)


# ============================================================================
# Public entry point
# ============================================================================

def investigate(
    insight: dict,
    start_date: str,
    end_date: str,
    base_cohort: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """Top-level investigation. Returns full where/when/why/what payload.

    Cached at the cached_query layer keyed on (insight_id, dates, cohort)
    for 30 minutes. Subsequent clicks hit the cache."""
    insight_id = insight.get("id", "unknown")
    cache_key = hashlib.sha256(
        json.dumps(
            [insight_id, start_date, end_date, base_cohort or []],
            sort_keys=True, default=str,
        ).encode()
    ).hexdigest()

    def _runner(_sql: str, _params: dict | None) -> list[dict]:
        where = _investigate_where(insight, start_date, end_date, base_cohort)
        when = _investigate_when(insight, start_date, end_date, base_cohort)

        llm_result = _llm_synthesize(insight, where, when)
        if llm_result:
            why_what_text, provider = llm_result
        else:
            why_what_text = _template_synthesize(insight, where, when)
            provider = "template"

        return [{
            "where": where,
            "when": when,
            "why_what": why_what_text,
            "source": provider,
            "insight": insight,
            "date_range": {"start": start_date, "end": end_date},
        }]

    rows = cached_query(
        sql=f"-- investigate:{cache_key}",
        params=None,
        runner=_runner,
        ttl_seconds=1800,  # 30 min
    )
    return rows[0]
