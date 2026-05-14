"""Saved funnels CRUD.

Funnels are scoped to the active connection profile. Switching profiles
shows a different list. This is intentional: event names differ across products.
"""
from fastapi import APIRouter, HTTPException

from .. import db
from ..config import get_active_config
from ..models.schemas import (
    SavedFunnelCreateRequest,
    SavedFunnelResponse,
    SavedFunnelUpdateRequest,
)

router = APIRouter()


def _require_profile_id() -> int:
    cfg = get_active_config()
    if cfg.profile_id is None:
        raise HTTPException(
            status_code=400,
            detail="Saved funnels require a saved connection profile. "
                   "Click your project name in the header → 'Add new connection' "
                   "and check 'Save as profile'.",
        )
    return cfg.profile_id


@router.get("/saved-funnels", response_model=list[SavedFunnelResponse])
def list_saved_funnels():
    pid = _require_profile_id()
    return db.list_saved_funnels(pid)


@router.post("/saved-funnels", response_model=SavedFunnelResponse)
def create_saved_funnel(req: SavedFunnelCreateRequest):
    pid = _require_profile_id()
    try:
        return db.create_saved_funnel(pid, req.name, req.config.model_dump())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/saved-funnels/{funnel_id}", response_model=SavedFunnelResponse)
def update_saved_funnel(funnel_id: int, req: SavedFunnelUpdateRequest):
    existing = db.get_saved_funnel(funnel_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Funnel not found.")
    # Authz: only allow updating funnels under the active profile.
    pid = _require_profile_id()
    if existing["profile_id"] != pid:
        raise HTTPException(status_code=403, detail="Funnel belongs to a different profile.")
    return db.update_saved_funnel(funnel_id, req.name, req.config.model_dump())


@router.delete("/saved-funnels/{funnel_id}")
def delete_saved_funnel(funnel_id: int):
    existing = db.get_saved_funnel(funnel_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Funnel not found.")
    pid = _require_profile_id()
    if existing["profile_id"] != pid:
        raise HTTPException(status_code=403, detail="Funnel belongs to a different profile.")
    db.delete_saved_funnel(funnel_id)
    return {"ok": True}
