"""System endpoints: cache stats, data freshness, etc.

Separated from connection.py because these are diagnostic/observability concerns,
not auth concerns. Different mental model.
"""
from datetime import datetime, timezone

from fastapi import APIRouter

from ..bigquery_client import run_query
from ..cache import cache_stats
from ..config import get_active_config
from ..sql import render

router = APIRouter()


@router.get("/cache/stats")
def stats():
    return cache_stats()


@router.get("/freshness")
def data_freshness():
    """Returns the timestamp of the most recent event in the dataset.

    Why this matters: Firebase's BigQuery export is daily. If your last event
    is 2 days old, the export is broken or the user expected streaming when
    they enabled daily. Showing a freshness badge in the UI prevents the
    "why is my dashboard empty" support ticket.

    We deliberately scan the last 3 days of shards only -- scanning the whole
    history just to find a max() would be wasteful.
    """
    cfg = get_active_config()
    sql = render(
        """
        SELECT
          TIMESTAMP_MICROS(MAX(event_timestamp)) AS latest_event,
          COUNT(DISTINCT _TABLE_SUFFIX) AS days_with_data
        FROM {EVENTS_TABLE}
        WHERE _TABLE_SUFFIX BETWEEN
          FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY))
          AND FORMAT_DATE('%Y%m%d', CURRENT_DATE())
        """,
        EVENTS_TABLE=cfg.events_table,
    )
    rows = run_query(sql, cache_ttl_seconds=600)  # cache 10min - freshness changes slowly
    if not rows or not rows[0].get("latest_event"):
        return {"status": "no_data", "latest_event": None, "hours_old": None}

    latest = rows[0]["latest_event"]
    if hasattr(latest, "isoformat"):
        latest_iso = latest.isoformat()
        # BQ returns timezone-aware UTC; if it's naive (shouldn't be), assume UTC.
        if latest.tzinfo is None:
            latest_dt = latest.replace(tzinfo=timezone.utc)
        else:
            latest_dt = latest
    else:
        latest_iso = str(latest)
        latest_dt = None

    hours_old = None
    if latest_dt is not None:
        delta = datetime.now(timezone.utc) - latest_dt
        hours_old = round(delta.total_seconds() / 3600, 1)

    # Status thresholds for the UI badge.
    if hours_old is None:
        status = "unknown"
    elif hours_old < 30:  # ~1 day, accounts for daily export lag
        status = "fresh"
    elif hours_old < 72:
        status = "stale"
    else:
        status = "broken"

    return {
        "status": status,
        "latest_event": latest_iso,
        "hours_old": hours_old,
        "days_with_data": rows[0].get("days_with_data", 0),
    }
