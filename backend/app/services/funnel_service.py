"""Funnel service. Cohort-aware in v0.4."""
from __future__ import annotations

from typing import Any, Optional

from ..bigquery_client import run_query
from ..config import get_active_config
from ..sql import cohort_clauses, load_sql, render
from .cohort_filter import compile_filters


def _build_step_aggregations(num_steps: int) -> str:
    lines = []
    for i in range(1, num_steps + 1):
        lines.append(f"  MIN(IF(event_name = @step_event_{i}, event_time, NULL)) AS s{i}_time")
    return ",\n".join(lines)


def _build_step_counts(num_steps: int, window_days: int) -> str:
    parts = ["  COUNT(DISTINCT IF(s1_time IS NOT NULL, user_pseudo_id, NULL)) AS step_1_users"]
    for i in range(2, num_steps + 1):
        cond = (
            f"s{i}_time IS NOT NULL "
            f"AND s{i}_time > s{i-1}_time "
            f"AND TIMESTAMP_DIFF(s{i}_time, s1_time, DAY) <= {window_days}"
        )
        parts.append(f"  COUNT(DISTINCT IF({cond}, user_pseudo_id, NULL)) AS step_{i}_users")
    return ",\n".join(parts)


def build_funnel(
    steps: list[str],
    start_date: str,
    end_date: str,
    window_days: int = 7,
    cohort: Optional[list[dict]] = None,
) -> dict[str, Any]:
    if len(steps) < 2:
        raise ValueError("Funnel needs at least 2 steps.")
    if len(steps) > 10:
        raise ValueError("Max 10 steps for MVP.")

    cfg = get_active_config()
    compiled = compile_filters(cohort)
    template = load_sql("funnel.sql")
    sql = render(
        template,
        EVENTS_TABLE=cfg.events_table,
        STEP_AGGREGATIONS=_build_step_aggregations(len(steps)),
        STEP_COUNTS=_build_step_counts(len(steps), window_days),
        **cohort_clauses(compiled.sql),
    )

    params: dict[str, Any] = {
        "start_date": start_date,
        "end_date": end_date,
        "step_events": steps,
        **compiled.params,
    }
    for i, ev in enumerate(steps, start=1):
        params[f"step_event_{i}"] = ev

    rows = run_query(sql, params)
    if not rows:
        return {"steps": [], "total_starting": 0}

    row = rows[0]
    starting = row.get("step_1_users", 0) or 0

    out_steps = []
    prev_users = None
    for i, ev in enumerate(steps, start=1):
        users = row.get(f"step_{i}_users", 0) or 0
        drop_off_pct = None
        if prev_users is not None and prev_users > 0:
            drop_off_pct = (prev_users - users) / prev_users
        conversion_from_start_pct = (users / starting) if starting else 0
        out_steps.append({
            "index": i,
            "event": ev,
            "users": users,
            "drop_off_from_prev_pct": drop_off_pct,
            "conversion_from_start_pct": conversion_from_start_pct,
        })
        prev_users = users

    return {
        "steps": out_steps,
        "total_starting": starting,
        "window_days": window_days,
        "date_range": {"start": start_date, "end": end_date},
        "cohort": cohort or [],
    }


def suggest_intermediate_steps(
    start_event: str,
    end_event: str,
    start_date: str,
    end_date: str,
    max_steps: int = 5,
) -> list[str]:
    """Find common events users hit between start and end, in completion order."""
    cfg = get_active_config()
    sql = f"""
    WITH journeys AS (
      SELECT user_pseudo_id, event_name, TIMESTAMP_MICROS(event_timestamp) AS t
      FROM {cfg.events_table}
      WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
    ),
    bounds AS (
      SELECT user_pseudo_id,
        MIN(IF(event_name = @start_event, t, NULL)) AS start_t,
        MIN(IF(event_name = @end_event,   t, NULL)) AS end_t
      FROM journeys
      WHERE event_name IN (@start_event, @end_event)
      GROUP BY user_pseudo_id
      HAVING start_t IS NOT NULL AND end_t IS NOT NULL AND end_t > start_t
    ),
    middle AS (
      SELECT j.event_name, COUNT(DISTINCT j.user_pseudo_id) AS users
      FROM journeys j
      JOIN bounds b USING (user_pseudo_id)
      WHERE j.t > b.start_t AND j.t < b.end_t
        AND j.event_name NOT IN (@start_event, @end_event)
      GROUP BY j.event_name
    )
    SELECT event_name FROM middle
    ORDER BY users DESC
    LIMIT @max_steps;
    """
    rows = run_query(sql, {
        "start_event": start_event, "end_event": end_event,
        "start_date": start_date, "end_date": end_date,
        "max_steps": max_steps,
    })
    middle = [r["event_name"] for r in rows]
    return [start_event] + middle + [end_event]
