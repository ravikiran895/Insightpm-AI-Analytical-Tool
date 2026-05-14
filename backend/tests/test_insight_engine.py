"""Tests for the insight engine: rule logic + date helpers."""
from datetime import date

from app.services.insight_engine import (
    _humanize_pct,
    _periods_from_range,
    _week_windows,
    rule_largest_funnel_dropoff,
)


class TestDateHelpers:
    def test_week_windows_correct_offsets(self):
        # On April 25, this week is Apr 18-24, last week is Apr 11-17
        this_s, this_e, last_s, last_e = _week_windows(date(2026, 4, 25))
        assert this_s == "20260418" and this_e == "20260424"
        assert last_s == "20260411" and last_e == "20260417"

    def test_periods_from_range_30_day(self):
        this_s, this_e, prev_s, prev_e = _periods_from_range("20260401", "20260430")
        assert this_s == "20260401" and this_e == "20260430"
        assert prev_e == "20260331"  # day before this_start
        assert prev_s == "20260302"  # 30 days back

    def test_periods_from_range_7_day(self):
        this_s, this_e, prev_s, prev_e = _periods_from_range("20260418", "20260424")
        assert prev_e == "20260417"
        assert prev_s == "20260411"  # 7 days back

    def test_periods_from_range_single_day(self):
        this_s, this_e, prev_s, prev_e = _periods_from_range("20260425", "20260425")
        assert prev_s == prev_e == "20260424"


class TestHumanize:
    def test_basic(self):
        assert _humanize_pct(0.143) == "14.3%"

    def test_zero(self):
        assert _humanize_pct(0) == "0.0%"

    def test_full(self):
        assert _humanize_pct(1.0) == "100.0%"


class TestFunnelDropoffRule:
    """rule_largest_funnel_dropoff is pure, no BQ -- test directly."""

    def test_finds_biggest_drop(self):
        funnel = [
            {"index": 1, "event": "session_start", "users": 1000,
             "drop_off_from_prev_pct": None, "conversion_from_start_pct": 1.0},
            {"index": 2, "event": "view_item", "users": 800,
             "drop_off_from_prev_pct": 0.20, "conversion_from_start_pct": 0.8},
            {"index": 3, "event": "add_to_cart", "users": 200,
             "drop_off_from_prev_pct": 0.75, "conversion_from_start_pct": 0.2},
            {"index": 4, "event": "purchase", "users": 150,
             "drop_off_from_prev_pct": 0.25, "conversion_from_start_pct": 0.15},
        ]
        finding = rule_largest_funnel_dropoff(funnel)
        assert finding is not None
        assert "add_to_cart" in finding.title
        assert finding.severity >= 0.7  # 75% drop -> severity 0.75
        assert finding.kind == "funnel"

    def test_no_finding_below_threshold(self):
        # All drops under 30% -- nothing should fire
        funnel = [
            {"index": 1, "event": "a", "users": 1000,
             "drop_off_from_prev_pct": None, "conversion_from_start_pct": 1.0},
            {"index": 2, "event": "b", "users": 900,
             "drop_off_from_prev_pct": 0.10, "conversion_from_start_pct": 0.9},
            {"index": 3, "event": "c", "users": 850,
             "drop_off_from_prev_pct": 0.056, "conversion_from_start_pct": 0.85},
        ]
        finding = rule_largest_funnel_dropoff(funnel)
        assert finding is None

    def test_single_step_no_finding(self):
        funnel = [
            {"index": 1, "event": "a", "users": 100,
             "drop_off_from_prev_pct": None, "conversion_from_start_pct": 1.0},
        ]
        assert rule_largest_funnel_dropoff(funnel) is None

    def test_handles_none_dropoffs_gracefully(self):
        # Step 1 always has None drop_off; rest may have None if no users
        funnel = [
            {"index": 1, "event": "a", "users": 1000,
             "drop_off_from_prev_pct": None, "conversion_from_start_pct": 1.0},
            {"index": 2, "event": "b", "users": 0,
             "drop_off_from_prev_pct": None, "conversion_from_start_pct": 0},
        ]
        # Should not crash even though step 2 has None drop_off
        finding = rule_largest_funnel_dropoff(funnel)
        assert finding is None  # No actionable finding
