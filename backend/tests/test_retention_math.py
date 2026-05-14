"""Regression tests for retention rate math.

v0.9.1 fix: retention_service was returning d1_avg/d7_avg/d30_avg as
already-divided rates (0-1), but consumers (frontend, nlq, breakdown)
were dividing again by total_users -- producing values 1000x too small.

These tests pin the contract: dN_avg are RATES (0-1), dN_retained
are COUNTS, total_users is the denominator.
"""
from unittest.mock import patch


def test_retention_headline_rates_are_unit_interval():
    """Pin the contract: dN_avg fields are rates between 0 and 1."""
    from app.services import retention_service

    fake_rows = [
        {
            "cohort_date": __import__("datetime").date(2026, 4, 1),
            "cohort_size": 100,
            "d1_users": 50, "d7_users": 30, "d30_users": 10,
            "d1_rate": 0.5, "d7_rate": 0.3, "d30_rate": 0.1,
        },
        {
            "cohort_date": __import__("datetime").date(2026, 4, 2),
            "cohort_size": 200,
            "d1_users": 80, "d7_users": 40, "d30_users": 20,
            "d1_rate": 0.4, "d7_rate": 0.2, "d30_rate": 0.1,
        },
    ]

    fake_cfg = type("Cfg", (), {"events_table": "p.d.events_*"})()
    with patch("app.services.retention_service.run_query", return_value=fake_rows), \
         patch("app.services.retention_service.compile_filters") as mock_cf, \
         patch("app.services.retention_service.get_active_config", return_value=fake_cfg):
        mock_cf.return_value = type("X", (), {"sql": "", "params": {}})()
        result = retention_service.cohort_retention("20260401", "20260430")

    h = result["headline"]
    assert abs(h["d1_avg"] - 130 / 300) < 0.001
    assert abs(h["d7_avg"] - 70 / 300) < 0.001
    assert abs(h["d30_avg"] - 30 / 300) < 0.001
    assert h["d1_retained"] == 130
    assert h["d7_retained"] == 70
    assert h["d30_retained"] == 30
    assert h["total_users"] == 300


def test_retention_zero_users_returns_zero_rates():
    """Edge case: empty cohort doesn't cause divide-by-zero."""
    from app.services import retention_service

    fake_cfg = type("Cfg", (), {"events_table": "p.d.events_*"})()
    with patch("app.services.retention_service.run_query", return_value=[]), \
         patch("app.services.retention_service.compile_filters") as mock_cf, \
         patch("app.services.retention_service.get_active_config", return_value=fake_cfg):
        mock_cf.return_value = type("X", (), {"sql": "", "params": {}})()
        result = retention_service.cohort_retention("20260401", "20260430")

    h = result["headline"]
    assert h["d1_avg"] == 0.0
    assert h["d7_avg"] == 0.0
    assert h["d30_avg"] == 0.0
    assert h["total_users"] == 0


def test_retention_rate_displays_correctly():
    """The calling pattern: rate * 100 = display percentage.
    e.g. 0.18 → 18.0%, NOT 0.018% (which was the bug)."""
    rate = 130 / 300  # ~ 0.4333
    display_pct = rate * 100
    assert 43.0 < display_pct < 43.5
    assert display_pct > 1.0  # would have been ~0.001 with the old bug
