from fastapi import APIRouter, Query

from ..models.schemas import CohortFilteredRequest
from ..services import retention_service

router = APIRouter()


@router.post("/retention")
def retention_post(req: CohortFilteredRequest):
    """POST variant accepts a cohort filter in the body."""
    return retention_service.cohort_retention(
        start_date=req.start_date,
        end_date=req.end_date,
        cohort=req.cohort,
    )


@router.get("/retention")
def retention_get(
    start_date: str = Query(..., pattern=r"^\d{8}$"),
    end_date: str = Query(..., pattern=r"^\d{8}$"),
):
    """GET variant for backwards compatibility (no cohort)."""
    return retention_service.cohort_retention(start_date, end_date)
