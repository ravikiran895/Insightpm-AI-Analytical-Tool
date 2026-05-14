"""Saved cohorts CRUD.

Cohorts are scoped to the active connection profile. Switching profiles
shows a different list. Same pattern as saved_funnels.
"""
from fastapi import APIRouter, HTTPException

from .. import db
from ..config import get_active_config
from ..models.schemas import (
    SavedCohortCreateRequest,
    SavedCohortResponse,
    SavedCohortUpdateRequest,
)
from ..services.cohort_filter import compile_filters

router = APIRouter()


def _require_profile_id() -> int:
    cfg = get_active_config()
    if cfg.profile_id is None:
        raise HTTPException(
            status_code=400,
            detail="Saved cohorts require a saved connection profile. "
                   "Click your project name in the header → 'Add new connection' "
                   "and check 'Save as profile'.",
        )
    return cfg.profile_id


def _validate_filters(filters: list[dict]) -> None:
    """Run the cohort filter compiler over the filters as a sanity check.
    This catches malformed filters at save time rather than at use time.

    The compiler also enforces the security allowlists, so we get a clean
    rejection of any tampered filter payloads."""
    try:
        compile_filters(filters)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid cohort filter: {e}",
        )


@router.get("/saved-cohorts", response_model=list[SavedCohortResponse])
def list_saved_cohorts():
    pid = _require_profile_id()
    return db.list_saved_cohorts(pid)


@router.post("/saved-cohorts", response_model=SavedCohortResponse)
def create_saved_cohort(req: SavedCohortCreateRequest):
    pid = _require_profile_id()
    _validate_filters(req.filters)
    try:
        return db.create_saved_cohort(pid, req.name, req.filters)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/saved-cohorts/{cohort_id}", response_model=SavedCohortResponse)
def update_saved_cohort(cohort_id: int, req: SavedCohortUpdateRequest):
    existing = db.get_saved_cohort(cohort_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Cohort not found.")
    pid = _require_profile_id()
    if existing["profile_id"] != pid:
        raise HTTPException(status_code=403, detail="Cohort belongs to a different profile.")
    _validate_filters(req.filters)
    return db.update_saved_cohort(cohort_id, req.name, req.filters)


@router.delete("/saved-cohorts/{cohort_id}")
def delete_saved_cohort(cohort_id: int):
    existing = db.get_saved_cohort(cohort_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Cohort not found.")
    pid = _require_profile_id()
    if existing["profile_id"] != pid:
        raise HTTPException(status_code=403, detail="Cohort belongs to a different profile.")
    db.delete_saved_cohort(cohort_id)
    return {"ok": True}
