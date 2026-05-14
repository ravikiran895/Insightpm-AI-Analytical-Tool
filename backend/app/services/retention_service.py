"""Retention service. Cohort-aware in v0.4. Math fixed in v0.9.1."""
from __future__ import annotations

from typing import Any, Optional

from ..bigquery_client import run_query
from ..config import get_active_config
from ..sql import cohort_clauses, load_sql, render
from .cohort_filter import compile_filters


def cohort_retention(
    start_date: str,
    end_date: str,
    cohort: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """Compute cohort retention with weighted-average headline.

    Math note (v0.9.1 fix):
    - SQL returns `dN_users` (count of users retained on day N from cohort)
      and `dN_rate` (already-computed rate per cohort).
    - Headline is the weighted average of per-cohort dN_users / total_size,
      which equals the overall percentage of cohorted users retained on dN.
    - Field naming (v0.9.1): we now return BOTH `d1_avg` (rate, 0-1) AND
      `d1_retained` (count) so consumers don't double-divide. Old `d1_avg`
      semantics changed from count to rate -- a small breaking change but the
      previous behavior produced wrong percentages on the frontend.
    """
    cfg = get_active_config()
    compiled = compile_filters(cohort)
    sql = render(
        load_sql("retention_cohort.sql"),
        EVENTS_TABLE=cfg.events_table,
        **cohort_clauses(compiled.sql),
    )
    rows = run_query(sql, {
        "start_date": start_date,
        "end_date": end_date,
        **compiled.params,
    })

    cohorts = []
    for r in rows:
        cohorts.append({
            "cohort_date": r["cohort_date"].isoformat() if r.get("cohort_date") else None,
            "cohort_size": r.get("cohort_size", 0),
            "d1_users": r.get("d1_users", 0),
            "d7_users": r.get("d7_users", 0),
            "d30_users": r.get("d30_users", 0),
            "d1_rate": float(r.get("d1_rate") or 0),
            "d7_rate": float(r.get("d7_rate") or 0),
            "d30_rate": float(r.get("d30_rate") or 0),
        })

    total_size = sum(c["cohort_size"] for c in cohorts) or 0
    total_d1 = sum(c["d1_users"] for c in cohorts)
    total_d7 = sum(c["d7_users"] for c in cohorts)
    total_d30 = sum(c["d30_users"] for c in cohorts)

    # _avg fields are RATES (0-1). _retained fields are COUNTS.
    # Frontends should multiply _avg by 100 to get a percentage; do not divide
    # _avg by total_users (it's already a per-user rate).
    if total_size > 0:
        d1_avg = total_d1 / total_size
        d7_avg = total_d7 / total_size
        d30_avg = total_d30 / total_size
    else:
        d1_avg = d7_avg = d30_avg = 0.0

    headline = {
        "d1_avg": d1_avg,           # rate, 0-1
        "d7_avg": d7_avg,           # rate, 0-1
        "d30_avg": d30_avg,         # rate, 0-1
        "d1_retained": total_d1,    # count
        "d7_retained": total_d7,    # count
        "d30_retained": total_d30,  # count
        "total_users": total_size,  # total cohorted users
    }

    return {"cohorts": cohorts, "headline": headline, "cohort_filter": cohort or []}
