"""
Active connection config.

Resolution order on startup:
  1. If a profile is marked is_default in SQLite, use it.
  2. Else if BQ_PROJECT_ID + BQ_DATASET_ID are set in env, use those (legacy
     path -- still works after upgrading from v0.2 without doing anything).
  3. Else no active config; user must POST /api/connect (which now optionally
     creates a profile).

The user-facing flow:
  - First time: connect once, check "save as profile". Server creates the profile
    and marks it default. Subsequent restarts auto-load it.
  - Switching projects: pick a different saved profile from a dropdown -> server
    swaps the active config, no restart needed.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class BQConfig:
    project_id: str
    dataset_id: str
    service_account_info: Optional[dict] = None
    profile_id: Optional[int] = None
    profile_name: Optional[str] = None

    @property
    def events_table(self) -> str:
        return f"`{self.project_id}.{self.dataset_id}.events_*`"


def _config_from_env() -> Optional[BQConfig]:
    project = os.getenv("BQ_PROJECT_ID")
    dataset = os.getenv("BQ_DATASET_ID")
    if not project or not dataset:
        return None
    sa_str = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    sa_info = json.loads(sa_str) if sa_str else None
    return BQConfig(project_id=project, dataset_id=dataset, service_account_info=sa_info)


_active: Optional[BQConfig] = None


def initialize_active_config() -> None:
    """Called from main.py on startup. Loads default profile or env fallback."""
    global _active
    # Lazy import: db needs project root on path, which is set up by FastAPI.
    from . import db
    db.init_db()
    profile = db.get_default_profile(with_credentials=True)
    if profile:
        _active = BQConfig(
            project_id=profile["project_id"],
            dataset_id=profile["dataset_id"],
            service_account_info=profile.get("service_account_info"),
            profile_id=profile["id"],
            profile_name=profile["name"],
        )
        return
    _active = _config_from_env()


def get_active_config() -> BQConfig:
    if _active is None:
        raise RuntimeError(
            "No BigQuery connection configured. POST /api/connect or save a profile."
        )
    return _active


def set_active_config(cfg: BQConfig) -> None:
    global _active
    _active = cfg


def get_active_config_or_none() -> Optional[BQConfig]:
    return _active


def frontend_origin() -> str:
    return os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
