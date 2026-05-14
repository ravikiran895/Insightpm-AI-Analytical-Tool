"""Connection + profile management.

Endpoints:
  POST   /api/connect          - One-shot connect (legacy). Optionally save as profile.
  GET    /api/connection       - Current active connection.
  GET    /api/profiles         - List saved profiles.
  POST   /api/profiles         - Create profile.
  POST   /api/profiles/{id}/use - Switch active connection to this profile.
  POST   /api/profiles/{id}/default - Mark as default (auto-load on startup).
  DELETE /api/profiles/{id}    - Delete profile.
"""
from fastapi import APIRouter, HTTPException

from .. import db
from ..bigquery_client import test_connection
from ..cache import invalidate_cache
from ..config import BQConfig, get_active_config_or_none, set_active_config
from ..models.schemas import (
    ConnectRequest,
    ConnectResponse,
    ProfileCreateRequest,
    ProfileResponse,
)

router = APIRouter()


@router.post("/connect", response_model=ConnectResponse)
def connect(req: ConnectRequest):
    cfg = BQConfig(
        project_id=req.project_id,
        dataset_id=req.dataset_id,
        service_account_info=req.service_account_json,
    )
    ok, msg = test_connection(cfg)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Could not connect: {msg}")

    # Optionally persist as a profile.
    profile_id = None
    if req.save_as:
        try:
            profile = db.create_profile(
                name=req.save_as,
                project_id=req.project_id,
                dataset_id=req.dataset_id,
                service_account_info=req.service_account_json,
                is_default=req.set_default,
            )
            profile_id = profile["id"]
            cfg.profile_id = profile_id
            cfg.profile_name = profile["name"]
            db.update_profile_last_used(profile_id)
        except Exception as e:  # noqa: BLE001
            # Connection works but profile-save failed (e.g. name collision).
            # Set the active config anyway, surface the problem.
            set_active_config(cfg)
            invalidate_cache()
            raise HTTPException(
                status_code=400,
                detail=f"Connected, but couldn't save profile: {e}. Try a different name.",
            )

    set_active_config(cfg)
    invalidate_cache()
    return ConnectResponse(ok=True, message="Connected.", profile_id=profile_id)


@router.get("/connection")
def current_connection():
    cfg = get_active_config_or_none()
    if cfg is None:
        return {"connected": False}
    return {
        "connected": True,
        "project_id": cfg.project_id,
        "dataset_id": cfg.dataset_id,
        "profile_id": cfg.profile_id,
        "profile_name": cfg.profile_name,
    }


@router.get("/profiles", response_model=list[ProfileResponse])
def list_profiles():
    return db.list_profiles()


@router.post("/profiles", response_model=ProfileResponse)
def create_profile(req: ProfileCreateRequest):
    """Create a profile WITHOUT testing the connection. Use /connect for test+save."""
    try:
        return db.create_profile(
            name=req.name,
            project_id=req.project_id,
            dataset_id=req.dataset_id,
            service_account_info=req.service_account_json,
            is_default=req.set_default,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/profiles/{profile_id}/use", response_model=ConnectResponse)
def use_profile(profile_id: int):
    """Switch active connection to this profile. The single-click switcher."""
    profile = db.get_profile(profile_id, with_credentials=True)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    cfg = BQConfig(
        project_id=profile["project_id"],
        dataset_id=profile["dataset_id"],
        service_account_info=profile.get("service_account_info"),
        profile_id=profile["id"],
        profile_name=profile["name"],
    )
    ok, msg = test_connection(cfg)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail=f"Profile '{profile['name']}' connection failed: {msg}",
        )

    set_active_config(cfg)
    invalidate_cache()
    db.update_profile_last_used(profile_id)
    return ConnectResponse(ok=True, message=f"Switched to '{profile['name']}'.", profile_id=profile_id)


@router.post("/profiles/{profile_id}/default")
def set_default(profile_id: int):
    profile = db.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")
    db.set_default_profile(profile_id)
    return {"ok": True}


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: int):
    if not db.delete_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found.")
    # If we just deleted the active one, blank it out.
    cfg = get_active_config_or_none()
    if cfg and cfg.profile_id == profile_id:
        from ..config import set_active_config as _set
        # Re-init from env if available; else nothing.
        from ..config import initialize_active_config
        initialize_active_config()
    return {"ok": True}
