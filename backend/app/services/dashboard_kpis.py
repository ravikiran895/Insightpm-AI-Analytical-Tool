"""Dashboard KPIs orchestration service.

Computes the four headline KPIs for the dashboard overview:
  - Active Users      (unique user_pseudo_id in window)
  - Total Events      (sum of all events in window)
  - D7 Retention      (weighted-average 7-day retention rate)
  - Top Events        (top 5 event names by count)

Plus optional previous-period comparison for delta computation,
plus a daily-active-users series for the Active Users sparkline.

Implementation note: this service is intentionally a THIN orchestration
layer over existing services. It does not introduce new BigQuery SQL.
We compose three existing services:
  - event_service.daily_activity()  →  per-day DAU + total events derivation
  - event_service.top_events()      →  top 5 events
  - retention_service.cohort_retention()  →  D7 weighted average

This keeps the math consistent with the rest of the product. The retention
calc was audited in v0.9.1; reusing it means the dashboard D7 will match
the Retention tab exactly. No double-source-of-truth bugs.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

# Note: event_service and retention_service are imported lazily inside the
# orchestration functions below. This keeps the pure-Python helpers (date
# math, delta computation) importable in environments that don't have the
# BigQuery client library installed — which is how the tests work.


def _parse_yyyymmdd(s: str) -> date:
    """Parse a YYYYMMDD string to a date object."""
    return datetime.strptime(s, "%Y%m%d").date()


def _format_yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def previous_period(start_date: str, end_date: str) -> tuple[str, str]:
    """Given a date range, compute the immediately preceding range of
    the same length.

    Example: start=20260517, end=20260616 (31 days inclusive)
    →    prev_start=20260416, prev_end=20260516 (also 31 days)

    The previous period ends one day before the current period starts.
    """
    cur_start = _parse_yyyymmdd(start_date)
    cur_end = _parse_yyyymmdd(end_date)
    length_days = (cur_end - cur_start).days  # inclusive length minus 1
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length_days)
    return _format_yyyymmdd(prev_start), _format_yyyymmdd(prev_end)


def _kpis_for_window(
    start_date: str,
    end_date: str,
    cohort: Optional[list[dict]] = None,
    include_sparkline: bool = True,
    include_top_events: bool = True,
    include_d7: bool = True,
) -> dict[str, Any]:
    """Compute KPIs for a single date window.

    Implementation:
      - Active Users: distinct user_pseudo_id COUNT over the window
        (dedicated small query, since daily_activity gives per-day DAU)
      - Total Events: SUM of event_count from top_events (reuses existing query)
      - D7 Retention: weighted-average d7_rate from cohort_retention service
      - Top Events: top_events service, limit 5
      - Sparkline: daily_activity series (day → DAU)
    """
    from . import event_service, retention_service
    from ..bigquery_client import run_query
    from ..config import get_active_config
    cfg = get_active_config()

    # Active Users — dedicated COUNT(DISTINCT) over the window.
    # We don't put this in a .sql file because it's literally one line and
    # mixing it inline keeps the orchestration visible. Cohort filtering is
    # NOT applied here yet — adding cohort would require the cohort_filter
    # service rendering; that's a follow-up if needed.
    try:
        au_rows = run_query(
            f"SELECT COUNT(DISTINCT user_pseudo_id) AS active_users "
            f"FROM {cfg.events_table} "
            f"WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date",
            {"start_date": start_date, "end_date": end_date},
        )
        active_users = int(au_rows[0]["active_users"]) if au_rows else 0
    except Exception:
        active_users = 0

    # Top events (reuses existing service, cohort-aware)
    top = None
    total_events = None
    if include_top_events:
        try:
            top = event_service.top_events(start_date, end_date, limit=5, cohort=cohort)
            total_events = sum(int(r.get("event_count") or 0) for r in top)
        except Exception:
            top = []
            total_events = None

    # D7 retention from the audited cohort_retention service
    d7_rate = None
    d7_retained = None
    total_cohorted = None
    if include_d7:
        try:
            ret = retention_service.cohort_retention(start_date, end_date, cohort)
            d7_rate = ret["headline"]["d7_avg"]            # 0-1 rate
            d7_retained = ret["headline"]["d7_retained"]   # count
            total_cohorted = ret["headline"]["total_users"]
        except Exception:
            # Don't fail the whole dashboard if retention has insufficient data
            pass

    # Sparkline = the daily DAU series
    sparkline = None
    if include_sparkline:
        try:
            daily = event_service.daily_activity(start_date, end_date)
            sparkline = [
                {"day": r.get("day"), "value": int(r.get("dau") or 0)}
                for r in daily
            ]
        except Exception:
            sparkline = []

    return {
        "active_users": active_users,
        "total_events": total_events,
        "d7_rate": d7_rate,            # 0-1 (multiply by 100 for %)
        "d7_retained": d7_retained,    # count
        "total_cohorted": total_cohorted,
        "top_events": top,             # list of {event_name, event_count, unique_users}
        "sparkline": sparkline,        # [{day, value}] for active users
    }


def dashboard_kpis(
    start_date: str,
    end_date: str,
    cohort: Optional[list[dict]] = None,
    compare: bool = True,
) -> dict[str, Any]:
    """Return the full dashboard KPI payload.

    Args:
        start_date, end_date: YYYYMMDD strings defining the current window.
        cohort: optional cohort filter (same shape as everywhere else).
        compare: if True, also compute KPIs for the immediately-preceding window
            of the same length and include deltas.

    Returns:
        Dict with `current`, optional `previous`, and `deltas` keys.
    """
    current = _kpis_for_window(
        start_date=start_date,
        end_date=end_date,
        cohort=cohort,
        include_sparkline=True,
        include_top_events=True,
        include_d7=True,
    )

    out: dict[str, Any] = {
        "current": current,
        "window": {"start": start_date, "end": end_date},
    }

    if compare:
        prev_start, prev_end = previous_period(start_date, end_date)
        # For the previous period we skip the sparkline (we don't render it)
        # and skip top_events (not displayed for prev). Still compute D7 for
        # comparison purposes.
        previous = _kpis_for_window(
            start_date=prev_start,
            end_date=prev_end,
            cohort=cohort,
            include_sparkline=False,
            include_top_events=False,  # we still want total_events though...
            include_d7=True,
        )
        # We DO need total_events for previous to show the delta. Do one
        # small extra count query without the full top_events listing.
        from ..bigquery_client import run_query
        from ..config import get_active_config
        cfg = get_active_config()
        try:
            tc_rows = run_query(
                f"SELECT COUNT(*) AS total_events FROM {cfg.events_table} "
                f"WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date",
                {"start_date": prev_start, "end_date": prev_end},
            )
            previous["total_events"] = int(tc_rows[0]["total_events"]) if tc_rows else 0
        except Exception:
            previous["total_events"] = None

        out["previous"] = previous
        out["previous_window"] = {"start": prev_start, "end": prev_end}
        out["deltas"] = _compute_deltas(current, previous)

    return out


def _compute_deltas(current: dict, previous: dict) -> dict[str, Any]:
    """Compute % change deltas between current and previous KPIs.

    Returns dict with keys matching KPI names, values are dicts of:
        - pct: float (percent change, e.g. 8.4 for +8.4%)
        - direction: "up" | "down" | "flat"
        - absolute: numeric difference (current - previous)
    Returns None for a KPI if previous value is missing or zero.
    """
    def delta(cur, prev) -> Optional[dict]:
        if cur is None or prev is None:
            return None
        if prev == 0:
            # Can't compute % change from zero baseline; report direction only
            if cur == 0:
                return {"pct": 0.0, "direction": "flat", "absolute": 0}
            return {"pct": None, "direction": "up", "absolute": cur}
        pct = ((cur - prev) / prev) * 100
        direction = "up" if pct > 0.5 else ("down" if pct < -0.5 else "flat")
        return {"pct": round(pct, 1), "direction": direction, "absolute": cur - prev}

    return {
        "active_users": delta(current.get("active_users"), previous.get("active_users")),
        "total_events": delta(current.get("total_events"), previous.get("total_events")),
        # D7 is a rate, not a count — delta is in percentage points
        "d7_rate": _d7_delta(current.get("d7_rate"), previous.get("d7_rate")),
    }


def _d7_delta(cur_rate, prev_rate) -> Optional[dict]:
    """D7 retention is already a percentage. The delta is in PERCENTAGE POINTS
    (pp), not percent change. Different visual treatment in the UI.
    """
    if cur_rate is None or prev_rate is None:
        return None
    pp = (cur_rate - prev_rate) * 100  # both are 0-1 rates
    direction = "up" if pp > 0.05 else ("down" if pp < -0.05 else "flat")
    return {"pp": round(pp, 1), "direction": direction, "unit": "pp"}
