"""Tests for dashboard KPIs orchestration helpers.

Tests focus on the pure-Python pieces that don't touch BigQuery:
  - previous_period() date math (off-by-one is the biggest risk)
  - _compute_deltas() math
  - _d7_delta() percentage-point math

The BigQuery-touching functions (_kpis_for_window, dashboard_kpis) are
covered by integration tests if needed; this module pins the math.
"""
from app.services.dashboard_kpis import (
    _compute_deltas,
    _d7_delta,
    previous_period,
)


# ============================================================
# previous_period — date math
# ============================================================

def test_previous_period_30_day_window():
    """30-day window: prev period is the 30 days immediately before."""
    prev_start, prev_end = previous_period("20260517", "20260616")
    # Current: May 17 → Jun 16 (31 days inclusive)
    # Previous: Apr 16 → May 16 (31 days inclusive, ends day before current starts)
    assert prev_end == "20260516"  # one day before current start
    assert prev_start == "20260416"  # 31 days before prev_end


def test_previous_period_7_day_window():
    """7-day window: prev period is the 7 days immediately before."""
    prev_start, prev_end = previous_period("20260610", "20260616")
    # Current: Jun 10 → Jun 16 (7 days inclusive)
    # Previous: Jun 3 → Jun 9
    assert prev_end == "20260609"
    assert prev_start == "20260603"


def test_previous_period_single_day():
    """Single-day window: prev period is the day before."""
    prev_start, prev_end = previous_period("20260616", "20260616")
    assert prev_start == "20260615"
    assert prev_end == "20260615"


def test_previous_period_crosses_month_boundary():
    """Window crossing a month: prev period also crosses correctly."""
    prev_start, prev_end = previous_period("20260601", "20260615")
    # Current: 15 days, prev should be 15 days ending May 31
    assert prev_end == "20260531"
    assert prev_start == "20260517"


def test_previous_period_crosses_year_boundary():
    """Window starting Jan 1: prev period crosses into previous year."""
    prev_start, prev_end = previous_period("20260101", "20260131")
    # Current: 31 days in January. Prev: 31 days ending Dec 31, 2025.
    assert prev_end == "20251231"
    assert prev_start == "20251201"


# ============================================================
# _compute_deltas — count/total deltas
# ============================================================

def test_delta_positive_change():
    """Current > previous → positive delta with 'up' direction."""
    current = {"active_users": 1080, "total_events": 2410000}
    previous = {"active_users": 1000, "total_events": 2150000}
    deltas = _compute_deltas(current, previous)
    assert deltas["active_users"]["pct"] == 8.0
    assert deltas["active_users"]["direction"] == "up"
    assert deltas["active_users"]["absolute"] == 80


def test_delta_negative_change():
    """Current < previous → negative delta with 'down' direction."""
    current = {"active_users": 920}
    previous = {"active_users": 1000}
    deltas = _compute_deltas(current, previous)
    assert deltas["active_users"]["pct"] == -8.0
    assert deltas["active_users"]["direction"] == "down"


def test_delta_flat_when_change_under_half_percent():
    """Tiny changes (<0.5%) report as 'flat' to avoid noisy ticker behavior."""
    current = {"active_users": 1002}
    previous = {"active_users": 1000}
    deltas = _compute_deltas(current, previous)
    assert deltas["active_users"]["direction"] == "flat"


def test_delta_zero_baseline_returns_special_case():
    """Previous=0, current>0 → can't compute % but direction is 'up'."""
    current = {"active_users": 100}
    previous = {"active_users": 0}
    deltas = _compute_deltas(current, previous)
    assert deltas["active_users"]["pct"] is None
    assert deltas["active_users"]["direction"] == "up"


def test_delta_missing_value_returns_none():
    """A None KPI in current OR previous → delta is None (not a crash)."""
    current = {"active_users": None, "total_events": 1000}
    previous = {"active_users": 100, "total_events": None}
    deltas = _compute_deltas(current, previous)
    assert deltas["active_users"] is None
    assert deltas["total_events"] is None


# ============================================================
# _d7_delta — percentage-point math (rates, not counts)
# ============================================================

def test_d7_delta_in_percentage_points():
    """D7 deltas are in PP, not percent change. 0.25 → 0.20 = -5pp."""
    delta = _d7_delta(0.20, 0.25)  # current=20%, previous=25%
    assert delta["pp"] == -5.0
    assert delta["direction"] == "down"
    assert delta["unit"] == "pp"


def test_d7_delta_positive_uptick():
    """Retention improved: 0.238 → 0.259 is +2.1pp."""
    delta = _d7_delta(0.259, 0.238)
    assert delta["pp"] == 2.1
    assert delta["direction"] == "up"


def test_d7_delta_flat_threshold():
    """Tiny rate changes (<0.05pp) report as flat."""
    delta = _d7_delta(0.2502, 0.2500)
    assert delta["direction"] == "flat"


def test_d7_delta_missing_returns_none():
    """Missing prev or current → None, never a crash."""
    assert _d7_delta(None, 0.25) is None
    assert _d7_delta(0.25, None) is None
    assert _d7_delta(None, None) is None
