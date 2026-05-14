"""
Property breakdowns.

A breakdown takes a chart spec + a "split by" field, finds the top-N distinct
values of that field in the date range, then runs the chart query once per
value. Returns results in a uniform shape the frontend can render as
side-by-side comparisons.

Why top-N values, not all values:
- A `device.operating_system` field can have 50+ distinct values (every minor
  iOS/Android version). Showing all of them is unreadable and expensive.
- We default to top-5 by user count. The user can request more via a param.

Why we run N separate queries instead of one big GROUP BY query:
- The funnel SQL is already complex. Pivoting it by an extra dimension would
  require generating N * num_steps aggregation columns dynamically, which is
  brittle.
- N parallel queries against BigQuery is fine for typical N (5-10). Each
  query is independently cached.
- Using cohort_filter as the splitting mechanism means breakdown reuses ALL
  the security guarantees of the cohort layer -- no new SQL injection surface.
"""
from __future__ import annotations

from typing import Any, Optional

from ..bigquery_client import run_query
from ..config import get_active_config
from . import event_service, funnel_service, retention_service
from .cohort_filter import _RAW_COLUMNS


def _resolve_field_type(field: str, hint: Optional[str] = None) -> str:
    """Decide whether `field` is a raw column, user_property, or event_param."""
    if hint in ("column", "user_property", "event_param"):
        return hint
    if field in _RAW_COLUMNS:
        return "column"
    # Default: user_property. (Event params are rarely used for breakdown; if
    # you need one, pass field_type explicitly from the frontend.)
    return "user_property"


def discover_breakdown_values(
    field: str,
    field_type: str,
    start_date: str,
    end_date: str,
    top_n: int = 5,
    base_cohort: Optional[list[dict]] = None,
) -> list[dict]:
    """Find the top-N values for the chosen breakdown field, by user count.

    Returns rows shaped like:
      [{"value": "ANDROID", "users": 4823}, {"value": "IOS", "users": 1209}, ...]

    Respects the base_cohort filter: if you've filtered to "country = US" globally
    and ask for a platform breakdown, we only return platform values present
    among US users.
    """
    cfg = get_active_config()

    # Build the value-extraction expression based on field_type.
    if field_type == "column":
        if field not in _RAW_COLUMNS:
            raise ValueError(f"Raw column not in allowlist: {field}")
        value_expr = field
        cte = ""
    elif field_type == "user_property":
        value_expr = (
            "(SELECT COALESCE(value.string_value, CAST(value.int_value AS STRING)) "
            "FROM UNNEST(user_properties) WHERE key = @bd_field)"
        )
        cte = ""
    elif field_type == "event_param":
        value_expr = (
            "(SELECT COALESCE(value.string_value, CAST(value.int_value AS STRING)) "
            "FROM UNNEST(event_params) WHERE key = @bd_field)"
        )
        cte = ""
    else:
        raise ValueError(f"Unknown field_type: {field_type}")

    # Apply base cohort if provided (re-using the same compiler).
    from .cohort_filter import compile_filters
    compiled = compile_filters(base_cohort)
    cohort_and = f"AND {compiled.sql}" if compiled.sql else ""

    sql = f"""
    SELECT
      {value_expr} AS value,
      COUNT(DISTINCT user_pseudo_id) AS users
    FROM {cfg.events_table}
    WHERE _TABLE_SUFFIX BETWEEN @start_date AND @end_date
      {cohort_and}
    GROUP BY value
    HAVING value IS NOT NULL AND value != ''
    ORDER BY users DESC
    LIMIT @top_n
    """

    params: dict[str, Any] = {
        "start_date": start_date,
        "end_date": end_date,
        "top_n": top_n,
        **compiled.params,
    }
    if field_type in ("user_property", "event_param"):
        params["bd_field"] = field

    return run_query(sql, params)


def funnel_breakdown(
    steps: list[str],
    start_date: str,
    end_date: str,
    breakdown_field: str,
    field_type: Optional[str] = None,
    window_days: int = 7,
    base_cohort: Optional[list[dict]] = None,
    top_n: int = 5,
) -> dict[str, Any]:
    """Run the funnel once per top-N value of breakdown_field.
    Each result is the standard funnel response, plus a 'series_label' field.
    """
    field_type = _resolve_field_type(breakdown_field, field_type)
    values = discover_breakdown_values(
        breakdown_field, field_type, start_date, end_date, top_n=top_n,
        base_cohort=base_cohort,
    )

    results = []
    for v in values:
        # Compose: base_cohort AND (breakdown_field = value)
        per_cohort = list(base_cohort or [])
        per_cohort.append({
            "field": breakdown_field,
            "field_type": field_type,
            "operator": "equals",
            "values": [v["value"]],
        })
        funnel_result = funnel_service.build_funnel(
            steps=steps,
            start_date=start_date,
            end_date=end_date,
            window_days=window_days,
            cohort=per_cohort,
        )
        results.append({
            "series_label": str(v["value"]),
            "series_users": int(v["users"]),
            **funnel_result,
        })

    return {
        "breakdown_field": breakdown_field,
        "breakdown_field_type": field_type,
        "series": results,
        "value_count": len(results),
    }


def retention_breakdown(
    start_date: str,
    end_date: str,
    breakdown_field: str,
    field_type: Optional[str] = None,
    base_cohort: Optional[list[dict]] = None,
    top_n: int = 5,
) -> dict[str, Any]:
    field_type = _resolve_field_type(breakdown_field, field_type)
    values = discover_breakdown_values(
        breakdown_field, field_type, start_date, end_date, top_n=top_n,
        base_cohort=base_cohort,
    )

    results = []
    for v in values:
        per_cohort = list(base_cohort or [])
        per_cohort.append({
            "field": breakdown_field,
            "field_type": field_type,
            "operator": "equals",
            "values": [v["value"]],
        })
        ret = retention_service.cohort_retention(start_date, end_date, cohort=per_cohort)
        h = ret["headline"]
        # d1_avg / d7_avg / d30_avg are already rates (v0.9.1 fix)
        results.append({
            "series_label": str(v["value"]),
            "series_users": int(v["users"]),
            "d1_rate": h["d1_avg"],
            "d7_rate": h["d7_avg"],
            "d30_rate": h["d30_avg"],
            "total_users": h["total_users"],
        })

    return {
        "breakdown_field": breakdown_field,
        "breakdown_field_type": field_type,
        "series": results,
        "value_count": len(results),
    }
