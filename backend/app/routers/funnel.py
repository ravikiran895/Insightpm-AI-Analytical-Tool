from fastapi import APIRouter

from ..models.schemas import FunnelRequest, FunnelSuggestRequest
from ..services import funnel_service

router = APIRouter()


@router.post("/funnel")
def build_funnel(req: FunnelRequest):
    return funnel_service.build_funnel(
        steps=req.steps,
        start_date=req.start_date,
        end_date=req.end_date,
        window_days=req.window_days,
        cohort=req.cohort,
    )


@router.post("/funnel/suggest")
def suggest_funnel(req: FunnelSuggestRequest):
    return {
        "steps": funnel_service.suggest_intermediate_steps(
            start_event=req.start_event,
            end_event=req.end_event,
            start_date=req.start_date,
            end_date=req.end_date,
            max_steps=req.max_steps,
        )
    }
