"""
Thin wrapper around the BigQuery SDK.

Why a wrapper:
- Centralized client construction (handles both file-based and inline credentials).
- One place for query parameter binding (forces all callers off string concat,
  which is the #1 way to ship a SQL injection bug from a "trusted" UI).
- Makes services testable: stub `run_query` in unit tests without a real BQ.
- Single integration point for caching (so every service gets it for free).
"""
from __future__ import annotations

from typing import Any, Optional

from google.cloud import bigquery
from google.oauth2 import service_account

from .cache import cached_query
from .config import BQConfig, get_active_config


def _build_client(cfg: BQConfig) -> bigquery.Client:
    """Build a fresh client for the given config. No caching here -- caching at
    this layer is fragile (key collisions when sa_info changes), and BQ client
    construction is cheap (~ms). The query result cache does the real work."""
    if cfg.service_account_info:
        creds = service_account.Credentials.from_service_account_info(cfg.service_account_info)
        return bigquery.Client(project=cfg.project_id, credentials=creds)
    # Falls back to GOOGLE_APPLICATION_CREDENTIALS / ADC.
    return bigquery.Client(project=cfg.project_id)


def get_client(cfg: BQConfig | None = None) -> bigquery.Client:
    return _build_client(cfg or get_active_config())


def _to_param(name: str, value: Any) -> bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter:
    if isinstance(value, list):
        # Infer element type from first item; assume homogeneous.
        sample = value[0] if value else ""
        bq_type = _infer_type(sample)
        return bigquery.ArrayQueryParameter(name, bq_type, value)
    return bigquery.ScalarQueryParameter(name, _infer_type(value), value)


def _infer_type(v: Any) -> str:
    if isinstance(v, bool):
        return "BOOL"
    if isinstance(v, int):
        return "INT64"
    if isinstance(v, float):
        return "FLOAT64"
    return "STRING"


def _run_uncached(sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    """The raw BigQuery executor. Use run_query() unless you need to bypass cache."""
    client = get_client()
    job_config = bigquery.QueryJobConfig()
    if params:
        job_config.query_parameters = [_to_param(k, v) for k, v in params.items()]
    job = client.query(sql, job_config=job_config)
    return [dict(row.items()) for row in job.result()]


def run_query(
    sql: str,
    params: dict[str, Any] | None = None,
    cache_ttl_seconds: Optional[int] = None,
    use_cache: bool = True,
) -> list[dict]:
    """Run a parameterized query and return rows as plain dicts.

    Caching is on by default with the cache module's default TTL (300s).
    Pass use_cache=False for endpoints where freshness matters more than cost
    (e.g. real-time DAU dashboards -- not a current concern).
    """
    if not use_cache:
        return _run_uncached(sql, params)
    return cached_query(sql, params, _run_uncached, ttl_seconds=cache_ttl_seconds)


def test_connection(cfg: BQConfig) -> tuple[bool, str]:
    """Cheap probe: does the dataset exist and is it readable?"""
    try:
        client = get_client(cfg)
        client.get_dataset(f"{cfg.project_id}.{cfg.dataset_id}")
        return True, "Connected."
    except Exception as e:  # noqa: BLE001 -- we want to surface any cause to the user
        return False, str(e)
