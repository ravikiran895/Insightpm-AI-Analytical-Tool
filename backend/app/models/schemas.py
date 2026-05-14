from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ConnectRequest(BaseModel):
    project_id: str
    dataset_id: str
    service_account_json: Optional[dict] = None
    # If set, persist as a saved profile after successful test.
    save_as: Optional[str] = None
    set_default: bool = False


class ConnectResponse(BaseModel):
    ok: bool
    message: str
    profile_id: Optional[int] = None


class ProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    project_id: str
    dataset_id: str
    service_account_json: Optional[dict] = None
    set_default: bool = False


class ProfileResponse(BaseModel):
    id: int
    name: str
    project_id: str
    dataset_id: str
    has_credentials: bool
    is_default: bool
    created_at: str
    last_used_at: Optional[str] = None


class DateRange(BaseModel):
    # YYYYMMDD strings to match _TABLE_SUFFIX format.
    start_date: str = Field(..., pattern=r"^\d{8}$")
    end_date: str = Field(..., pattern=r"^\d{8}$")


class FunnelRequest(DateRange):
    steps: list[str] = Field(..., min_length=2, max_length=10)
    window_days: int = Field(default=7, ge=1, le=90)
    cohort: Optional[list[dict[str, Any]]] = None


class FunnelSuggestRequest(DateRange):
    start_event: str
    end_event: str
    max_steps: int = Field(default=5, ge=2, le=8)


class CohortFilteredRequest(DateRange):
    """Generic request shape for cohort-aware GET-style endpoints (events, retention)."""
    cohort: Optional[list[dict[str, Any]]] = None


class SavedFunnelConfig(BaseModel):
    """Serialized funnel state. Stored as JSON in SQLite."""
    steps: list[str]
    window_days: int = 7
    cohort: Optional[list[dict[str, Any]]] = None
    # Optional defaults; the user can still override at view time.
    default_start_date: Optional[str] = Field(default=None, pattern=r"^\d{8}$")
    default_end_date: Optional[str] = Field(default=None, pattern=r"^\d{8}$")


class SavedFunnelCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    config: SavedFunnelConfig


class SavedFunnelUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    config: SavedFunnelConfig


class SavedFunnelResponse(BaseModel):
    id: int
    name: str
    profile_id: int
    config: SavedFunnelConfig
    created_at: str


class FunnelBreakdownRequest(DateRange):
    steps: list[str] = Field(..., min_length=2, max_length=10)
    window_days: int = Field(default=7, ge=1, le=90)
    breakdown_field: str
    field_type: Optional[str] = None  # column | user_property | event_param
    base_cohort: Optional[list[dict[str, Any]]] = None
    top_n: int = Field(default=5, ge=2, le=10)


class RetentionBreakdownRequest(DateRange):
    breakdown_field: str
    field_type: Optional[str] = None
    base_cohort: Optional[list[dict[str, Any]]] = None
    top_n: int = Field(default=5, ge=2, le=10)


class UserProfileRequest(DateRange):
    user_id: str = Field(..., min_length=1, max_length=200)


# ----------------------------------------------------------------------------
# Saved cohorts (Phase 9)
# ----------------------------------------------------------------------------
class SavedCohortCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    filters: list[dict[str, Any]] = Field(..., min_length=1)


class SavedCohortUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    filters: list[dict[str, Any]] = Field(..., min_length=1)


class SavedCohortResponse(BaseModel):
    id: int
    name: str
    profile_id: int
    filters: list[dict[str, Any]]
    created_at: str


# ----------------------------------------------------------------------------
# Where/When/Why investigator (Phase 9 - USP 2)
# ----------------------------------------------------------------------------
class InvestigateRequest(DateRange):
    """Request body for /api/insights/investigate.

    The frontend sends back the insight it wants investigated, plus the date
    range that was active. We need both because the investigator runs MULTIPLE
    queries to dimensionalize the insight.
    """
    insight: dict[str, Any]
    base_cohort: Optional[list[dict[str, Any]]] = None


class InsightsRequest(BaseModel):
    funnel_start_event: Optional[str] = None
    funnel_end_event: Optional[str] = None
    funnel_steps: Optional[list[dict[str, Any]]] = None
    # Date range for the analysis window. If absent, falls back to weekly defaults.
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{8}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{8}$")


class NLQRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)


class SqlPreviewRequest(BaseModel):
    kind: str  # one of: top_events, retention, funnel, daily_activity
    start_date: str = Field(..., pattern=r"^\d{8}$")
    end_date: str = Field(..., pattern=r"^\d{8}$")
    limit: Optional[int] = None
    funnel_steps: Optional[list[str]] = None
    window_days: Optional[int] = None


class ExplainInsightRequest(BaseModel):
    """Request body for /api/insights/explain.

    The frontend sends back the full insight object it received from
    /api/insights, plus the date range that was analyzed. We don't store
    insights server-side, so the frontend is responsible for echoing them
    back when asking for explanation -- this keeps the flow stateless.
    """
    insight: dict[str, Any]
    start_date: str = Field(..., pattern=r"^\d{8}$")
    end_date: str = Field(..., pattern=r"^\d{8}$")
