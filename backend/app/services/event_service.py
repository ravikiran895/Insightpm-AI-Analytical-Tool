"""Event service. Cohort-aware in v0.4."""
from __future__ import annotations

from typing import Optional

from ..bigquery_client import run_query
from ..config import get_active_config
from ..sql import cohort_clauses, load_sql, render
from .cohort_filter import compile_filters


def top_events(
    start_date: str,
    end_date: str,
    limit: int = 50,
    cohort: Optional[list[dict]] = None,
) -> list[dict]:
    cfg = get_active_config()
    compiled = compile_filters(cohort)
    sql = render(
        load_sql("top_events.sql"),
        EVENTS_TABLE=cfg.events_table,
        **cohort_clauses(compiled.sql),
    )
    params = {
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
        **compiled.params,
    }
    return run_query(sql, params)


def daily_activity(start_date: str, end_date: str) -> list[dict]:
    cfg = get_active_config()
    sql = render(load_sql("daily_activity.sql"), EVENTS_TABLE=cfg.events_table)
    rows = run_query(sql, {"start_date": start_date, "end_date": end_date})
    for r in rows:
        if r.get("day"):
            r["day"] = r["day"].isoformat()
    return rows


def event_param_sample(
    event_name: str, param_key: str, start_date: str, end_date: str, limit: int = 100
) -> list[dict]:
    cfg = get_active_config()
    sql = render(load_sql("event_params.sql"), EVENTS_TABLE=cfg.events_table)
    rows = run_query(sql, {
        "event_name": event_name,
        "param_key": param_key,
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
    })
    for r in rows:
        if r.get("event_time"):
            r["event_time"] = r["event_time"].isoformat()
    return rows


def list_filterable_fields(start_date: str, end_date: str) -> dict:
    """Discover what user_properties / event_params / columns are available
    for filtering. The frontend uses this to build a friendly cohort UI.

    Cheap query: scans only DISTINCT keys from the most recent ~1 day of data
    so the filter UI loads fast."""
    cfg = get_active_config()
    sql = f"""
    WITH recent AS (
      SELECT * FROM {cfg.events_table}
      WHERE _TABLE_SUFFIX = @end_date
      LIMIT 50000
    )
    SELECT 'user_property' AS field_type, key AS field
    FROM recent, UNNEST(user_properties)
    GROUP BY field
    UNION ALL
    SELECT 'event_param' AS field_type, key AS field
    FROM recent, UNNEST(event_params)
    GROUP BY field
    ORDER BY field_type, field
    """
    rows = run_query(sql, {"end_date": end_date}, cache_ttl_seconds=1800)

    # Always include the standard "raw column" fields too — these are stable
    # and don't need a query to discover.
    raw_columns = [
        {"field": "geo.country", "field_type": "column", "label": "Country"},
        {"field": "geo.region", "field_type": "column", "label": "Region"},
        {"field": "geo.city", "field_type": "column", "label": "City"},
        {"field": "platform", "field_type": "column", "label": "Platform"},
        {"field": "device.category", "field_type": "column", "label": "Device category"},
        {"field": "device.operating_system", "field_type": "column", "label": "OS"},
        {"field": "app_info.version", "field_type": "column", "label": "App version"},
        {"field": "traffic_source.source", "field_type": "column", "label": "Traffic source"},
        {"field": "traffic_source.medium", "field_type": "column", "label": "Traffic medium"},
    ]
    user_props = [{"field": r["field"], "field_type": "user_property", "label": r["field"]}
                  for r in rows if r["field_type"] == "user_property"]
    event_params = [{"field": r["field"], "field_type": "event_param", "label": r["field"]}
                    for r in rows if r["field_type"] == "event_param"]

    return {
        "columns": raw_columns,
        "user_properties": user_props,
        "event_params": event_params,
    }
