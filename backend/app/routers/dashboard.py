from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..models.schemas import DateRange
from ..services import dashboard_kpis as dashboard_service

router = APIRouter()


class DashboardKpisRequest(DateRange):
    """Request payload for dashboard KPIs.

    Inherits start_date / end_date from DateRange (YYYYMMDD strings).
    """
    cohort: Optional[list[dict]] = None
    compare: bool = True


@router.post("/dashboard/kpis")
def get_dashboard_kpis(req: DashboardKpisRequest):
    """Returns headline KPIs for the dashboard overview, optionally with
    previous-period comparison.

    Response shape:
        {
          "current": {
            "active_users": int,
            "total_events": int,
            "d7_rate": float (0-1),
            "d7_retained": int,
            "total_cohorted": int,
            "top_events": [{event_name, event_count, unique_users}, ...],
            "sparkline": [{day, value}, ...]
          },
          "previous": {... same shape, no sparkline/top_events ...},
          "deltas": {
            "active_users": {pct, direction, absolute},
            "total_events": {pct, direction, absolute},
            "d7_rate": {pp, direction, unit: "pp"}
          },
          "window": {start, end},
          "previous_window": {start, end}
        }

    The frontend should treat any KPI field as nullable — if BigQuery
    fails for one (e.g., D7 has insufficient data), only that field is
    null and the rest still render.
    """
    return dashboard_service.dashboard_kpis(
        start_date=req.start_date,
        end_date=req.end_date,
        cohort=req.cohort,
        compare=req.compare,
    )
