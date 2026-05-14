"""Breakdown endpoints — split a chart by a property dimension."""
from fastapi import APIRouter

from ..models.schemas import FunnelBreakdownRequest, RetentionBreakdownRequest
from ..services import breakdown_service

router = APIRouter()


@router.post("/funnel/breakdown")
def funnel_breakdown(req: FunnelBreakdownRequest):
    return breakdown_service.funnel_breakdown(
        steps=req.steps,
        start_date=req.start_date,
        end_date=req.end_date,
        breakdown_field=req.breakdown_field,
        field_type=req.field_type,
        window_days=req.window_days,
        base_cohort=req.base_cohort,
        top_n=req.top_n,
    )


@router.post("/retention/breakdown")
def retention_breakdown(req: RetentionBreakdownRequest):
    return breakdown_service.retention_breakdown(
        start_date=req.start_date,
        end_date=req.end_date,
        breakdown_field=req.breakdown_field,
        field_type=req.field_type,
        base_cohort=req.base_cohort,
        top_n=req.top_n,
    )
