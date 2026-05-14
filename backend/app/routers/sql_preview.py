"""SQL preview endpoint.

Trust comes from auditability. PMs that can see the SQL behind a chart will
believe the numbers; ones who can't, won't.

Returns the rendered SQL with parameters substituted INTO COMMENTS at the top
(not into the query itself -- that would defeat the security of parameterization).
This way the SQL shown matches what BigQuery actually executes, just with
human-readable annotation.
"""
from fastapi import APIRouter, HTTPException

from ..config import get_active_config
from ..models.schemas import SqlPreviewRequest
from ..services import funnel_service
from ..sql import load_sql, render

router = APIRouter()


def _annotate(sql: str, params: dict) -> str:
    """Prepend a /* params */ block so the user sees what values were bound."""
    if not params:
        return sql
    lines = ["/* Parameters bound for this query:"]
    for k, v in params.items():
        if isinstance(v, list):
            v_str = "[" + ", ".join(repr(x) for x in v[:5])
            if len(v) > 5:
                v_str += f", ... +{len(v) - 5} more"
            v_str += "]"
        else:
            v_str = repr(v)
        lines.append(f"   @{k} = {v_str}")
    lines.append("*/")
    return "\n".join(lines) + "\n\n" + sql


@router.post("/sql-preview")
def sql_preview(req: SqlPreviewRequest):
    """Return the SQL that would run for a given chart kind + inputs.

    We never execute it -- this endpoint is read-only for the SQL string itself.
    """
    cfg = get_active_config()
    kind = req.kind

    if kind == "top_events":
        sql = render(load_sql("top_events.sql"), EVENTS_TABLE=cfg.events_table)
        params = {
            "start_date": req.start_date,
            "end_date": req.end_date,
            "limit": req.limit or 50,
        }
        return {"sql": _annotate(sql, params)}

    if kind == "retention":
        sql = render(load_sql("retention_cohort.sql"), EVENTS_TABLE=cfg.events_table)
        params = {"start_date": req.start_date, "end_date": req.end_date}
        return {"sql": _annotate(sql, params)}

    if kind == "funnel":
        if not req.funnel_steps or len(req.funnel_steps) < 2:
            raise HTTPException(status_code=400, detail="funnel_steps with 2+ events required.")
        steps = req.funnel_steps
        sql = render(
            load_sql("funnel.sql"),
            EVENTS_TABLE=cfg.events_table,
            STEP_AGGREGATIONS=funnel_service._build_step_aggregations(len(steps)),
            STEP_COUNTS=funnel_service._build_step_counts(len(steps), req.window_days or 7),
        )
        params: dict = {
            "start_date": req.start_date,
            "end_date": req.end_date,
            "step_events": steps,
        }
        for i, ev in enumerate(steps, start=1):
            params[f"step_event_{i}"] = ev
        return {"sql": _annotate(sql, params)}

    if kind == "daily_activity":
        sql = render(load_sql("daily_activity.sql"), EVENTS_TABLE=cfg.events_table)
        params = {"start_date": req.start_date, "end_date": req.end_date}
        return {"sql": _annotate(sql, params)}

    raise HTTPException(status_code=400, detail=f"Unknown chart kind: {kind}")
