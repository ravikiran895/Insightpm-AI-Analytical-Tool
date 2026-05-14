"""
User Behavior Profiler — the headline USP.

Given a user_pseudo_id, returns:
  1. A structured journey (events, sessions, funnels they completed/abandoned)
  2. Computed behavior metrics (session count, engagement minutes, retention status)
  3. An AI-generated narrative ("This user opened the app 4 times in week 1...")
  4. Recommendations specific to this user's pattern

Why this is the moat:
- SaaS tools redact user_pseudo_id behind enterprise tiers, or cap per-user
  analysis behind a meter. We can iterate on a single user for $0.
- Per-user LLM narratives at SaaS economics would cost cents per user. At
  Haiku pricing with our context size, it's well under $0.005 per user.
- Most importantly: the recommendation step uses YOUR product knowledge
  (funnel definitions you've saved, cohorts you've defined). A SaaS tool
  cannot know about AlphaReturns specifically.

Privacy boundary:
- The user_pseudo_id is a Firebase-generated random ID; it's not real PII
  by itself, but combined with other event params it can become identifying.
- We never log user_pseudo_id. The journey rows fetched include it but we
  drop it before passing to the LLM.
- If the caller asks for behavior across MULTIPLE users at once, we sample
  to a max of 5 to keep per-user analysis the dominant use case.
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from ..bigquery_client import run_query
from ..cache import cached_query
from ..config import get_active_config
from ..sql import load_sql, render
from .llm_client import call_llm

log = logging.getLogger("insightpm.profiler")


_SYSTEM_PROMPT = """You are a product analyst writing a behavioral biography of a single user, based on their event journey in a Firebase Analytics dataset.

You will be given:
- Computed behavioral metrics (session count, lifespan, top events, etc.)
- A summary of their event journey (events with timestamps)
- Optional context about funnels they completed or dropped from

Write a narrative in this exact structure:

**Story** (2-3 sentences): What this user did, when, and what stands out about their behavior. Use specific numbers and event names.

**Pattern**: What kind of user is this? Compare to common patterns (one-and-done explorer, engaged power user, drift-off user, returning visitor, etc.).

**Recommendations** (1-2 bullet points): What action would this kind of user benefit from? Or, what should the PM investigate based on this user's behavior?

Strict rules:
- Reference specific events and numbers from the data. NEVER invent.
- Use hedging when interpreting motivation: "appears to", "may indicate", "is consistent with".
- Keep the whole response under 200 words. PMs are busy.
- Don't repeat the raw metrics verbatim — interpret them.
- If the data is too sparse to draw conclusions, say so directly. Don't fill with fluff."""


def fetch_journey(
    user_id: str,
    start_date: str,
    end_date: str,
    event_limit: int = 200,
) -> list[dict]:
    """Fetch all events for a user in the window. Cached 1 hour."""
    cfg = get_active_config()
    sql = render(load_sql("user_journey.sql"), EVENTS_TABLE=cfg.events_table)
    rows = run_query(
        sql,
        {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "event_limit": event_limit,
        },
        cache_ttl_seconds=3600,
    )
    # Coerce timestamps to ISO for JSON serialization.
    for r in rows:
        if r.get("event_time"):
            t = r["event_time"]
            if hasattr(t, "isoformat"):
                r["event_time"] = t.isoformat()
    return rows


def compute_metrics(journey: list[dict]) -> dict[str, Any]:
    """Behavioral metrics derived purely from the journey rows."""
    if not journey:
        return {
            "event_count": 0, "session_count": 0,
            "total_engagement_minutes": 0,
            "first_seen": None, "last_seen": None,
            "active_days": 0, "lifespan_days": 0,
            "top_events": [], "platforms": [],
            "country": None,
        }

    sessions = {r["session_id"] for r in journey if r.get("session_id")}
    countries = {r["country"] for r in journey if r.get("country")}
    platforms = list({r["platform"] for r in journey if r.get("platform")})

    engagement_msec_total = sum(
        (r.get("engagement_msec") or 0) for r in journey
    )

    # Per-day uniques
    days = {r["event_time"][:10] for r in journey if r.get("event_time")}

    # Date span
    sorted_times = sorted(r["event_time"] for r in journey if r.get("event_time"))
    first = sorted_times[0]
    last = sorted_times[-1]
    try:
        first_dt = datetime.fromisoformat(first)
        last_dt = datetime.fromisoformat(last)
        lifespan_days = (last_dt.date() - first_dt.date()).days
    except (ValueError, TypeError):
        lifespan_days = 0

    # Top events
    event_counter = Counter(r["event_name"] for r in journey if r.get("event_name"))
    top_events = [{"event": e, "count": c} for e, c in event_counter.most_common(8)]

    return {
        "event_count": len(journey),
        "session_count": len(sessions),
        "total_engagement_minutes": round(engagement_msec_total / 60000, 1),
        "first_seen": first,
        "last_seen": last,
        "active_days": len(days),
        "lifespan_days": lifespan_days,
        "top_events": top_events,
        "platforms": platforms,
        "country": next(iter(countries), None) if countries else None,
        "app_version": journey[0].get("app_version"),
    }


def classify_pattern(metrics: dict, journey: list[dict]) -> dict[str, Any]:
    """Lightweight rule-based pattern classifier. Used both standalone and
    as input to the LLM narrative."""
    if metrics["event_count"] == 0:
        return {"label": "no_data", "confidence": 1.0, "description": "No events found in this window."}

    # One-and-done: very few events, single session, short lifespan
    if metrics["session_count"] <= 1 and metrics["event_count"] < 10:
        return {
            "label": "one_and_done",
            "confidence": 0.8,
            "description": "Opened the app once and didn't return.",
        }

    # Engaged power user: many sessions, lots of engagement, multiple days
    if metrics["session_count"] >= 10 and metrics["active_days"] >= 7:
        return {
            "label": "power_user",
            "confidence": 0.9,
            "description": "Frequent and sustained engagement -- a power user.",
        }

    # Drift-off: started strong, no recent activity
    # Heuristic: lifespan >= 5 days AND no events in the last 30% of the window
    if metrics["lifespan_days"] >= 5:
        # Check if last_seen is recent relative to lifespan
        try:
            first_dt = datetime.fromisoformat(metrics["first_seen"])
            last_dt = datetime.fromisoformat(metrics["last_seen"])
            now = datetime.now(timezone.utc)
            days_since_last = (now - last_dt.replace(tzinfo=timezone.utc) if last_dt.tzinfo is None else now - last_dt).days
            if days_since_last > metrics["lifespan_days"] * 0.5:
                return {
                    "label": "drifted_off",
                    "confidence": 0.7,
                    "description": "Active for a stretch, then went quiet.",
                }
        except (ValueError, TypeError):
            pass

    # Returning visitor: multiple sessions across multiple days
    if metrics["session_count"] >= 3 and metrics["active_days"] >= 3:
        return {
            "label": "returning_visitor",
            "confidence": 0.7,
            "description": "Comes back regularly, moderate engagement.",
        }

    # Casual: somewhere in between
    return {
        "label": "casual",
        "confidence": 0.5,
        "description": "Light, occasional usage.",
    }


def _generate_narrative_with_llm(
    metrics: dict,
    pattern: dict,
    journey: list[dict],
) -> Optional[str]:
    """Returns the narrative text, or None if no LLM available."""
    # Sample timeline: first 8 events, last 4 events to show arc.
    if len(journey) <= 12:
        sampled = journey
    else:
        sampled = journey[:8] + journey[-4:]

    timeline_lines = []
    for r in sampled:
        ev = r.get("event_name", "?")
        t = (r.get("event_time") or "")[:19]
        page = r.get("screen_name") or r.get("page_title") or ""
        suffix = f" ({page})" if page else ""
        timeline_lines.append(f"  - {t} {ev}{suffix}")
    timeline_str = "\n".join(timeline_lines)
    if len(journey) > 12:
        timeline_str += f"\n  [... {len(journey) - 12} events omitted from middle ...]"

    user_prompt = f"""User behavior data for one user (user_pseudo_id redacted):

Metrics:
  - Total events: {metrics['event_count']}
  - Sessions: {metrics['session_count']}
  - Active days: {metrics['active_days']} (over a {metrics['lifespan_days']}-day lifespan)
  - Total engagement: {metrics['total_engagement_minutes']} minutes
  - Country: {metrics.get('country', 'unknown')}
  - Platforms: {', '.join(metrics.get('platforms', [])) or 'unknown'}
  - App version: {metrics.get('app_version', 'unknown')}

Pattern (rule-based classification): {pattern['label']} - {pattern['description']}

Top events for this user:
{chr(10).join(f'  - {e["event"]}: {e["count"]} times' for e in metrics['top_events'][:6])}

Sampled timeline:
{timeline_str}

Now write the Story / Pattern / Recommendations narrative."""

    result = call_llm(
        system=_SYSTEM_PROMPT,
        user_message=user_prompt,
        max_tokens=400,
    )
    if result is None:
        return None
    text, provider = result
    return (text, provider)


def _generate_narrative_template(metrics: dict, pattern: dict) -> str:
    """Deterministic fallback narrative. Useful even without LLM, but less rich."""
    label = pattern["label"]
    top_event = metrics["top_events"][0]["event"] if metrics["top_events"] else "no events"

    if label == "no_data":
        return (
            "**Story**: No events found for this user in the selected date range.\n\n"
            "**Pattern**: Insufficient data.\n\n"
            "**Recommendations**: Widen the date range, or verify the user_pseudo_id is correct."
        )

    base = (
        f"**Story**: This user generated {metrics['event_count']} events across "
        f"{metrics['session_count']} session(s) over {metrics['active_days']} active "
        f"day(s) (lifespan: {metrics['lifespan_days']} days). Most frequent action: "
        f"{top_event}.\n\n"
    )

    pattern_text = {
        "one_and_done": "**Pattern**: A 'one-and-done' user — opened the app, did very little, didn't come back. "
                        "This is the most common drop-off pattern in any product.\n\n"
                        "**Recommendations**:\n"
                        "- Investigate why your onboarding flow doesn't hook this segment in their first session.\n"
                        "- Compare retention by acquisition source — paid vs organic users often differ here.",

        "power_user": "**Pattern**: A power user — sustained, high engagement across many days. These users drive the bulk of your usage.\n\n"
                      "**Recommendations**:\n"
                      "- Identify what onboarding actions correlate with becoming a power user (use the 'aha moment' analysis).\n"
                      "- Consider giving this segment beta access to new features for early feedback.",

        "drifted_off": "**Pattern**: Drifted off — was engaged at first, then went quiet. This is the highest-leverage churn pattern: you had them, then lost them.\n\n"
                       "**Recommendations**:\n"
                       "- Look at events in the days before they went quiet — was there a friction point?\n"
                       "- Check whether feature releases or content changes coincided with their drop-off.",

        "returning_visitor": "**Pattern**: A returning visitor — comes back occasionally with moderate engagement. The middle of the funnel — not lost, not loyal yet.\n\n"
                             "**Recommendations**:\n"
                             "- This segment converts to power users with the right nudge. Identify what your top users did at this stage.\n"
                             "- Push notifications or email digests aimed at this group often have outsized ROI.",

        "casual": "**Pattern**: Casual / light user — uses the app occasionally without strong commitment.\n\n"
                  "**Recommendations**:\n"
                  "- Investigate value-prop clarity in your messaging — casual users often don't understand the full benefit.\n"
                  "- Compare retention by the events this user did not do — is there a key activation event they're missing?",
    }.get(label, "**Pattern**: Atypical pattern. Not enough signal to classify confidently.\n\n"
                 "**Recommendations**: Use the breakdown features to compare this user's segment against your power users.")

    return base + pattern_text


def fetch_aggregate_metrics(
    user_id: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Fetch totals for the user across the WHOLE window, not capped by
    journey limit. v0.9.1 fix: previously metrics like event_count and
    engagement minutes were computed from the truncated journey list (max
    200 events), so a user with 500 events would show '200 events' and
    undercounted engagement.

    Returns a dict of accurate aggregates that override journey-derived
    metrics where they exist.
    """
    cfg = get_active_config()
    sql = f"""
    SELECT
      COUNT(*) AS total_events,
      COUNT(DISTINCT (
        SELECT value.int_value
        FROM UNNEST(event_params)
        WHERE key = 'ga_session_id'
      )) AS total_sessions,
      COUNT(DISTINCT DATE(TIMESTAMP_MICROS(event_timestamp))) AS active_days,
      MIN(TIMESTAMP_MICROS(event_timestamp)) AS first_seen,
      MAX(TIMESTAMP_MICROS(event_timestamp)) AS last_seen,
      SUM(
        IFNULL((
          SELECT value.int_value
          FROM UNNEST(event_params)
          WHERE key = 'engagement_time_msec'
        ), 0)
      ) AS total_engagement_msec
    FROM {cfg.events_table}
    WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
      AND user_pseudo_id = @user_id
    """
    rows = run_query(sql, {
        "user_id": user_id,
        "start_date": start_date,
        "end_date": end_date,
    }, cache_ttl_seconds=3600)
    if not rows:
        return {
            "event_count_total": 0,
            "session_count_total": 0,
            "active_days_total": 0,
            "engagement_minutes_total": 0,
            "first_seen_total": None,
            "last_seen_total": None,
        }
    r = rows[0]
    first = r.get("first_seen")
    last = r.get("last_seen")
    return {
        "event_count_total": int(r.get("total_events") or 0),
        "session_count_total": int(r.get("total_sessions") or 0),
        "active_days_total": int(r.get("active_days") or 0),
        "engagement_minutes_total": round((r.get("total_engagement_msec") or 0) / 60000, 1),
        "first_seen_total": first.isoformat() if first and hasattr(first, "isoformat") else first,
        "last_seen_total": last.isoformat() if last and hasattr(last, "isoformat") else last,
    }


def profile_user(
    user_id: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """The main entry: fetch + analyze + narrate. Returns everything the
    frontend needs to render the profile."""
    if not user_id or len(user_id) > 200:
        raise ValueError("user_id must be a non-empty string under 200 chars")

    journey = fetch_journey(user_id, start_date, end_date)
    metrics = compute_metrics(journey)

    # Override journey-truncated metrics with accurate full-window aggregates.
    # The journey is capped at 200 events for display + LLM context, but
    # metrics (event count, sessions, lifespan, engagement) need to reflect
    # the whole window. v0.9.1 fix.
    try:
        agg = fetch_aggregate_metrics(user_id, start_date, end_date)
        metrics["event_count"] = agg["event_count_total"]
        metrics["session_count"] = agg["session_count_total"]
        metrics["active_days"] = agg["active_days_total"]
        metrics["total_engagement_minutes"] = agg["engagement_minutes_total"]
        if agg["first_seen_total"]:
            metrics["first_seen"] = agg["first_seen_total"]
        if agg["last_seen_total"]:
            metrics["last_seen"] = agg["last_seen_total"]
            # Recompute lifespan based on accurate first/last seen
            try:
                first_dt = datetime.fromisoformat(metrics["first_seen"])
                last_dt = datetime.fromisoformat(metrics["last_seen"])
                metrics["lifespan_days"] = (last_dt.date() - first_dt.date()).days
            except (ValueError, TypeError):
                pass
    except Exception as e:  # noqa: BLE001
        log.warning(f"Aggregate metrics fetch failed for user {user_id[:8]}...: {e}")
        # Fall back to journey-derived metrics (potentially truncated)

    pattern = classify_pattern(metrics, journey)

    # LLM narrative (or fallback)
    llm_result = _generate_narrative_with_llm(metrics, pattern, journey)
    if llm_result is not None:
        narrative, narrative_source = llm_result  # provider name: "gemini" or "anthropic"
    else:
        narrative = _generate_narrative_template(metrics, pattern)
        narrative_source = "template"

    return {
        "user_id": user_id,
        "metrics": metrics,
        "pattern": pattern,
        "narrative": narrative,
        "narrative_source": narrative_source,
        "journey_sample": journey[:50],  # don't bloat the response
        "journey_total_events": len(journey),
        "date_range": {"start": start_date, "end": end_date},
    }


def find_recent_users(start_date: str, end_date: str, limit: int = 20) -> list[dict]:
    """Helper: list a few recent active users so the PM has something to click
    on. Returns user IDs + lightweight stats. We deliberately don't expose
    full enumeration of users to avoid making this look like a list-mining
    interface.

    Strategy: pull users by event count desc (most active first) so the
    examples are interesting."""
    cfg = get_active_config()
    sql = f"""
    SELECT
      user_pseudo_id,
      COUNT(*) AS event_count,
      MIN(TIMESTAMP_MICROS(event_timestamp)) AS first_seen,
      MAX(TIMESTAMP_MICROS(event_timestamp)) AS last_seen,
      COUNT(DISTINCT DATE(TIMESTAMP_MICROS(event_timestamp))) AS active_days
    FROM {cfg.events_table}
    WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
    GROUP BY user_pseudo_id
    ORDER BY event_count DESC
    LIMIT @limit
    """
    rows = run_query(sql, {"start_date": start_date, "end_date": end_date, "limit": limit})
    out = []
    for r in rows:
        out.append({
            "user_id": r["user_pseudo_id"],
            "event_count": r["event_count"],
            "first_seen": r["first_seen"].isoformat() if r.get("first_seen") else None,
            "last_seen": r["last_seen"].isoformat() if r.get("last_seen") else None,
            "active_days": r["active_days"],
        })
    return out
