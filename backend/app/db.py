"""
Local SQLite database. Stores:
  - connection_profiles: saved BigQuery connections (project + dataset + sa_json)
  - saved_funnels: future use (Phase 3)
  - saved_reports: future use

Why SQLite (vs JSON file):
- We'll need a real DB for Phase 3 anyway (saved cohorts, funnels with metadata).
- ACID guarantees -- no torn writes if the user clicks Save while another tab
  is reading.
- No external dependency: sqlite3 ships with Python.

Why no encryption on the sa_json column:
- This is a local internal tool. Anyone with file access to the laptop can read
  your Downloads folder where the JSON originated. Encrypting just this column
  is security theater.
- If you want real encryption, encrypt the whole DB file at the OS level
  (BitLocker on Windows, FileVault on Mac).

Storage location:
- ~/.insightpm/insightpm.db on Unix/Mac
- C:/Users/<user>/.insightpm/insightpm.db on Windows
- Created on first startup. Survives app upgrades.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


def _db_path() -> Path:
    home = Path.home() / ".insightpm"
    home.mkdir(parents=True, exist_ok=True)
    return home / "insightpm.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS connection_profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    project_id      TEXT    NOT NULL,
    dataset_id      TEXT    NOT NULL,
    sa_json         TEXT,                      -- nullable: can use ADC instead
    is_default      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    last_used_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_profiles_default ON connection_profiles(is_default);

-- Reserved for Phase 3: saved funnels.
CREATE TABLE IF NOT EXISTS saved_funnels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    profile_id      INTEGER NOT NULL REFERENCES connection_profiles(id) ON DELETE CASCADE,
    config_json     TEXT    NOT NULL,         -- {steps, window_days, ...}
    created_at      TEXT    NOT NULL,
    UNIQUE(name, profile_id)
);

-- Saved cohort filters. Same scoping rules as saved_funnels: tied to a profile,
-- CASCADE deletes with the profile. Cohort definitions are profile-specific
-- because event_param and user_property names vary across products.
CREATE TABLE IF NOT EXISTS saved_cohorts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    profile_id      INTEGER NOT NULL REFERENCES connection_profiles(id) ON DELETE CASCADE,
    filters_json    TEXT    NOT NULL,         -- JSON-encoded list of cohort filter dicts
    created_at      TEXT    NOT NULL,
    UNIQUE(name, profile_id)
);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Idempotent: safe to call on every app start."""
    with _connect() as c:
        c.executescript(_SCHEMA)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_profile(row: sqlite3.Row) -> dict[str, Any]:
    sa = row["sa_json"]
    return {
        "id": row["id"],
        "name": row["name"],
        "project_id": row["project_id"],
        "dataset_id": row["dataset_id"],
        # We surface a flag instead of the raw JSON. Frontend doesn't need the secret.
        "has_credentials": sa is not None and sa != "",
        "is_default": bool(row["is_default"]),
        "created_at": row["created_at"],
        "last_used_at": row["last_used_at"],
    }


def list_profiles() -> list[dict[str, Any]]:
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM connection_profiles ORDER BY is_default DESC, last_used_at DESC NULLS LAST, name"
        ).fetchall()
        return [_row_to_profile(r) for r in rows]


def get_profile(profile_id: int, *, with_credentials: bool = False) -> Optional[dict[str, Any]]:
    with _connect() as c:
        row = c.execute(
            "SELECT * FROM connection_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if not row:
            return None
        out = _row_to_profile(row)
        if with_credentials and row["sa_json"]:
            out["service_account_info"] = json.loads(row["sa_json"])
        return out


def get_default_profile(*, with_credentials: bool = False) -> Optional[dict[str, Any]]:
    with _connect() as c:
        row = c.execute(
            "SELECT * FROM connection_profiles WHERE is_default = 1 LIMIT 1"
        ).fetchone()
        if not row:
            return None
        out = _row_to_profile(row)
        if with_credentials and row["sa_json"]:
            out["service_account_info"] = json.loads(row["sa_json"])
        return out


def create_profile(
    name: str,
    project_id: str,
    dataset_id: str,
    service_account_info: Optional[dict] = None,
    is_default: bool = False,
) -> dict[str, Any]:
    sa_json = json.dumps(service_account_info) if service_account_info else None
    with _connect() as c:
        if is_default:
            c.execute("UPDATE connection_profiles SET is_default = 0")
        cur = c.execute(
            """INSERT INTO connection_profiles
               (name, project_id, dataset_id, sa_json, is_default, created_at, last_used_at)
               VALUES (?, ?, ?, ?, ?, ?, NULL)""",
            (name, project_id, dataset_id, sa_json, 1 if is_default else 0, _now_iso()),
        )
        new_id = cur.lastrowid
    profile = get_profile(new_id)
    assert profile is not None
    return profile


def update_profile_last_used(profile_id: int) -> None:
    with _connect() as c:
        c.execute(
            "UPDATE connection_profiles SET last_used_at = ? WHERE id = ?",
            (_now_iso(), profile_id),
        )


def set_default_profile(profile_id: int) -> None:
    with _connect() as c:
        c.execute("UPDATE connection_profiles SET is_default = 0")
        c.execute(
            "UPDATE connection_profiles SET is_default = 1 WHERE id = ?", (profile_id,)
        )


def delete_profile(profile_id: int) -> bool:
    with _connect() as c:
        cur = c.execute(
            "DELETE FROM connection_profiles WHERE id = ?", (profile_id,)
        )
        return cur.rowcount > 0


# ============================================================================
# Saved funnels
# ============================================================================
# A "saved funnel" is a serialized funnel configuration: steps, window_days,
# cohort filters, optional date range. Tied to a connection profile so that
# switching profiles doesn't show funnels from a different dataset.
#
# Why scoped per-profile: event names differ across products. A funnel for
# AlphaReturns won't make sense pointed at a different Firebase export.

def list_saved_funnels(profile_id: int) -> list[dict[str, Any]]:
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM saved_funnels WHERE profile_id = ? ORDER BY name",
            (profile_id,),
        ).fetchall()
        return [_row_to_funnel(r) for r in rows]


def get_saved_funnel(funnel_id: int) -> Optional[dict[str, Any]]:
    with _connect() as c:
        row = c.execute(
            "SELECT * FROM saved_funnels WHERE id = ?", (funnel_id,)
        ).fetchone()
        return _row_to_funnel(row) if row else None


def create_saved_funnel(profile_id: int, name: str, config: dict) -> dict[str, Any]:
    with _connect() as c:
        cur = c.execute(
            """INSERT INTO saved_funnels (name, profile_id, config_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (name, profile_id, json.dumps(config), _now_iso()),
        )
        new_id = cur.lastrowid
    out = get_saved_funnel(new_id)
    assert out is not None
    return out


def update_saved_funnel(funnel_id: int, name: str, config: dict) -> Optional[dict[str, Any]]:
    with _connect() as c:
        c.execute(
            "UPDATE saved_funnels SET name = ?, config_json = ? WHERE id = ?",
            (name, json.dumps(config), funnel_id),
        )
    return get_saved_funnel(funnel_id)


def delete_saved_funnel(funnel_id: int) -> bool:
    with _connect() as c:
        cur = c.execute("DELETE FROM saved_funnels WHERE id = ?", (funnel_id,))
        return cur.rowcount > 0


def _row_to_funnel(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "profile_id": row["profile_id"],
        "config": json.loads(row["config_json"]),
        "created_at": row["created_at"],
    }


# ============================================================================
# Saved cohorts (Phase 9)
# ============================================================================
# A "saved cohort" is a named list of cohort filter dicts. Same shape as the
# `cohort` field passed to filter-aware endpoints (events, retention, funnel).
# Stored per-profile because field names (user_properties, event_params) vary
# between products.

def list_saved_cohorts(profile_id: int) -> list[dict[str, Any]]:
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM saved_cohorts WHERE profile_id = ? ORDER BY name",
            (profile_id,),
        ).fetchall()
        return [_row_to_cohort(r) for r in rows]


def get_saved_cohort(cohort_id: int) -> Optional[dict[str, Any]]:
    with _connect() as c:
        row = c.execute(
            "SELECT * FROM saved_cohorts WHERE id = ?", (cohort_id,)
        ).fetchone()
        return _row_to_cohort(row) if row else None


def create_saved_cohort(profile_id: int, name: str, filters: list[dict]) -> dict[str, Any]:
    with _connect() as c:
        cur = c.execute(
            """INSERT INTO saved_cohorts (name, profile_id, filters_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (name, profile_id, json.dumps(filters), _now_iso()),
        )
        new_id = cur.lastrowid
    out = get_saved_cohort(new_id)
    assert out is not None
    return out


def update_saved_cohort(cohort_id: int, name: str, filters: list[dict]) -> Optional[dict[str, Any]]:
    with _connect() as c:
        c.execute(
            "UPDATE saved_cohorts SET name = ?, filters_json = ? WHERE id = ?",
            (name, json.dumps(filters), cohort_id),
        )
    return get_saved_cohort(cohort_id)


def delete_saved_cohort(cohort_id: int) -> bool:
    with _connect() as c:
        cur = c.execute("DELETE FROM saved_cohorts WHERE id = ?", (cohort_id,))
        return cur.rowcount > 0


def _row_to_cohort(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "profile_id": row["profile_id"],
        "filters": json.loads(row["filters_json"]),
        "created_at": row["created_at"],
    }
