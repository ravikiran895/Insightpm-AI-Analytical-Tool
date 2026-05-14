from fastapi import APIRouter, Query

from ..models.schemas import CohortFilteredRequest
from ..services import event_service

router = APIRouter()


@router.post("/events")
def get_top_events_post(req: CohortFilteredRequest):
    """POST variant accepts a cohort filter in the body."""
    return {"events": event_service.top_events(
        start_date=req.start_date,
        end_date=req.end_date,
        cohort=req.cohort,
    )}


@router.get("/events")
def get_top_events_get(
    start_date: str = Query(..., pattern=r"^\d{8}$"),
    end_date: str = Query(..., pattern=r"^\d{8}$"),
    limit: int = Query(50, ge=1, le=200),
):
    """GET variant for backwards compatibility (no cohort)."""
    return {"events": event_service.top_events(start_date, end_date, limit)}


@router.get("/activity")
def get_daily_activity(
    start_date: str = Query(..., pattern=r"^\d{8}$"),
    end_date: str = Query(..., pattern=r"^\d{8}$"),
):
    return {"daily": event_service.daily_activity(start_date, end_date)}


@router.get("/cohort-fields")
def get_cohort_fields(
    start_date: str = Query(..., pattern=r"^\d{8}$"),
    end_date: str = Query(..., pattern=r"^\d{8}$"),
):
    """Returns the list of fields the user can filter on, organized by type."""
    return event_service.list_filterable_fields(start_date, end_date)
