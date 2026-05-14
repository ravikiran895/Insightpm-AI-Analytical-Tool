"""
Shared pytest fixtures.

Goals:
- Every test gets an isolated SQLite DB (temp dir).
- No test touches real BigQuery -- run_query is patched at the service layer.
- Tests are fast: <1s per test, full suite <5s.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Make the app importable. Tests run from repo root via `pytest`.
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture
def temp_home(monkeypatch, tmp_path):
    """Redirect ~/.insightpm to a temp dir. Each test gets a fresh DB."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
    # Force a fresh import path for db so our HOME override takes effect.
    import importlib
    from app import db
    importlib.reload(db)
    db.init_db()
    yield tmp_path


@pytest.fixture
def fake_bq(monkeypatch):
    """Patch run_query so tests don't hit BigQuery.

    Yields a list -- callers append (sql_substring, return_value) tuples.
    Match is by substring on the SQL; the FIRST matching tuple wins.
    """
    matchers: list[tuple[str, list[dict]]] = []

    def fake_run(sql, params=None, cache_ttl_seconds=None, use_cache=True):
        for substring, ret in matchers:
            if substring in sql:
                return ret
        # Default: empty result. Avoids accidental network calls.
        return []

    # Patch every place run_query is imported FROM.
    import app.bigquery_client
    monkeypatch.setattr(app.bigquery_client, "run_query", fake_run)

    # Service modules import run_query directly — patch their references too.
    for mod_path in [
        "app.services.event_service",
        "app.services.funnel_service",
        "app.services.retention_service",
        "app.services.breakdown_service",
        "app.services.insight_engine",
        "app.services.anomaly_explainer",
    ]:
        try:
            mod = __import__(mod_path, fromlist=["run_query"])
            if hasattr(mod, "run_query"):
                monkeypatch.setattr(mod, "run_query", fake_run)
        except (ImportError, AttributeError):
            pass

    yield matchers


@pytest.fixture
def active_config(monkeypatch):
    """Set up an active BQ config so services that call get_active_config() work."""
    from app import config

    cfg = config.BQConfig(
        project_id="test-project",
        dataset_id="analytics_test",
        service_account_info=None,
        profile_id=None,
        profile_name=None,
    )
    monkeypatch.setattr(config, "_active", cfg)
    yield cfg
