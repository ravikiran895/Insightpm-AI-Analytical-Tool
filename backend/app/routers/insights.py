from datetime import date

from fastapi import APIRouter

from ..models.schemas import ExplainInsightRequest, InsightsRequest, InvestigateRequest
from ..services import anomaly_explainer, insight_engine, investigator

router = APIRouter()


@router.post("/insights")
def insights(req: InsightsRequest):
    date_range = None
    if req.start_date and req.end_date:
        date_range = (req.start_date, req.end_date)
    findings = insight_engine.run_insights(
        today=date.today(),
        funnel_steps=req.funnel_steps,
        funnel_start_event=req.funnel_start_event,
        funnel_end_event=req.funnel_end_event,
        date_range=date_range,
    )
    return {"insights": [f.__dict__ for f in findings]}


@router.post("/insights/explain")
def explain(req: ExplainInsightRequest):
    return anomaly_explainer.explain_insight(
        insight=req.insight,
        date_range=(req.start_date, req.end_date),
    )


@router.post("/insights/investigate")
def investigate(req: InvestigateRequest):
    """Where/When/Why investigation -- USP 2.

    Takes a fired insight, runs ~6 targeted queries to dimensionalize it,
    then asks an LLM to synthesize a hypothesis + recommendation.
    Cached for 30 minutes per (insight_id, date_range, cohort).
    """
    return investigator.investigate(
        insight=req.insight,
        start_date=req.start_date,
        end_date=req.end_date,
        base_cohort=req.base_cohort,
    )
