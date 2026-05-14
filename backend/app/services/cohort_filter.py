"""
Cohort filter compiler.

Translates structured cohort filters into BigQuery WHERE clause fragments and
parameter dictionaries. The output is meant to be inlined into our existing
SQL templates via a {COHORT_FILTER} placeholder.

Why a compiler (not just string-building):
- User-supplied values MUST go through query parameters. Hardcoding them is a
  SQL injection risk even with a "trusted" UI -- defense in depth.
- Field names (event_param keys, user property keys) come from user input too,
  but they go into UNNEST subqueries with a parameter, so they're safe.
- Operators (=, !=, IN, contains) are validated against an allowlist.

Filter structure (frontend sends this, JSON):
  {
    "field": "country",                # the user property key OR event param
    "field_type": "user_property",     # one of: user_property | event_param | column
    "operator": "equals",              # one of: equals | not_equals | in | contains | starts_with
    "values": ["IN", "US"]
  }

A cohort is a list of filters, AND-ed together. (No OR for now — UI is simpler.)

Special case: when the user filters on `event_param` for a non-funnel chart,
"the user did event X with param Y = Z" semantics applies -- it filters to the
USERS who have at least one such event, not to the events themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# Allowlist of operators. Anything else is rejected.
_OPERATORS = {"equals", "not_equals", "in", "not_in", "contains", "starts_with"}

# Allowlist of "raw column" filters that don't need UNNEST (they're at the row level
# of the events_* table). Anything else MUST go through user_properties or event_params.
_RAW_COLUMNS = {
    "platform",            # ANDROID / IOS / WEB
    "device.category",     # mobile / tablet / desktop  (dotted path -> safe lookup)
    "device.operating_system",
    "geo.country",
    "geo.region",
    "geo.city",
    "app_info.version",
    "app_info.id",
    "traffic_source.source",
    "traffic_source.medium",
    "traffic_source.name",
}


@dataclass
class CompiledFilter:
    """A WHERE clause fragment + the params it requires."""
    sql: str
    params: dict[str, Any]


def compile_filters(filters: list[dict] | None, prefix: str = "f") -> CompiledFilter:
    """Compile a list of cohort filters into a single AND-ed WHERE fragment.

    `prefix` is used to name the generated query parameters so they don't
    collide with the host query's existing parameters. e.g. prefix='f' produces
    @f0_v0, @f0_v1, @f1_v0, ...

    Returns CompiledFilter("", {}) when filters is empty -- the caller can
    safely concat this to its own WHERE clause with " AND ".
    """
    if not filters:
        return CompiledFilter(sql="", params={})

    fragments: list[str] = []
    params: dict[str, Any] = {}

    for i, f in enumerate(filters):
        frag, p = _compile_one(f, name_prefix=f"{prefix}{i}")
        if frag:
            fragments.append(f"({frag})")
            params.update(p)

    if not fragments:
        return CompiledFilter(sql="", params={})

    return CompiledFilter(sql=" AND ".join(fragments), params=params)


def _compile_one(f: dict, name_prefix: str) -> tuple[str, dict[str, Any]]:
    field = (f.get("field") or "").strip()
    field_type = (f.get("field_type") or "").strip()
    operator = (f.get("operator") or "equals").strip()
    values = f.get("values") or []

    # ---- Validation ----
    if not field:
        raise ValueError("Filter missing 'field'")
    if field_type not in {"user_property", "event_param", "column"}:
        raise ValueError(f"Filter field_type must be one of user_property|event_param|column, got: {field_type}")
    if operator not in _OPERATORS:
        raise ValueError(f"Filter operator must be one of {_OPERATORS}, got: {operator}")
    if not isinstance(values, list) or len(values) == 0:
        raise ValueError("Filter 'values' must be a non-empty list")
    # All values must be primitive types we can bind.
    for v in values:
        if not isinstance(v, (str, int, float, bool)):
            raise ValueError(f"Unsupported filter value type: {type(v).__name__}")

    # ---- Field expression ----
    if field_type == "column":
        if field not in _RAW_COLUMNS:
            raise ValueError(f"Raw column filter not allowed: {field}")
        # Dotted-path fields like 'geo.country' are real STRUCT accesses in GA4
        # schema -- safe to inline since we validate against an allowlist.
        field_expr = field
    elif field_type == "user_property":
        # Pull from user_properties array. Try string_value first, then int_value.
        # We add the param key as a query param so the field name is also bound.
        key_param = f"{name_prefix}_key"
        field_expr = (
            f"(SELECT COALESCE(value.string_value, CAST(value.int_value AS STRING)) "
            f"FROM UNNEST(user_properties) WHERE key = @{key_param})"
        )
    elif field_type == "event_param":
        key_param = f"{name_prefix}_key"
        field_expr = (
            f"(SELECT COALESCE(value.string_value, CAST(value.int_value AS STRING)) "
            f"FROM UNNEST(event_params) WHERE key = @{key_param})"
        )
    else:
        raise ValueError(f"Unhandled field_type: {field_type}")

    # ---- Operator + value binding ----
    params: dict[str, Any] = {}
    if field_type in ("user_property", "event_param"):
        params[f"{name_prefix}_key"] = field

    if operator == "equals":
        v_param = f"{name_prefix}_v0"
        params[v_param] = str(values[0])
        sql = f"{field_expr} = @{v_param}"
    elif operator == "not_equals":
        v_param = f"{name_prefix}_v0"
        params[v_param] = str(values[0])
        sql = f"({field_expr} IS NULL OR {field_expr} != @{v_param})"
    elif operator == "in":
        v_param = f"{name_prefix}_vs"
        params[v_param] = [str(v) for v in values]
        sql = f"{field_expr} IN UNNEST(@{v_param})"
    elif operator == "not_in":
        v_param = f"{name_prefix}_vs"
        params[v_param] = [str(v) for v in values]
        sql = f"({field_expr} IS NULL OR {field_expr} NOT IN UNNEST(@{v_param}))"
    elif operator == "contains":
        v_param = f"{name_prefix}_v0"
        params[v_param] = f"%{values[0]}%"
        sql = f"{field_expr} LIKE @{v_param}"
    elif operator == "starts_with":
        v_param = f"{name_prefix}_v0"
        params[v_param] = f"{values[0]}%"
        sql = f"{field_expr} LIKE @{v_param}"
    else:
        raise ValueError(f"Unhandled operator: {operator}")  # pragma: no cover

    return sql, params


def humanize_filter(f: dict) -> str:
    """Human-readable description of a filter, for surfacing in insights/UI."""
    field = f.get("field", "?")
    op = f.get("operator", "equals")
    values = f.get("values") or []
    op_label = {
        "equals": "=", "not_equals": "≠", "in": "in", "not_in": "not in",
        "contains": "contains", "starts_with": "starts with",
    }.get(op, op)
    if op in ("in", "not_in"):
        v_str = "[" + ", ".join(repr(v) for v in values[:3]) + ("...]" if len(values) > 3 else "]")
    else:
        v_str = repr(values[0]) if values else ""
    return f"{field} {op_label} {v_str}"
