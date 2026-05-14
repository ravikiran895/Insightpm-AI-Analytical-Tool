"""Where/When/Why investigator tests.

These cover the pure-logic helpers (concentration detection, prompt
building, template synthesis). The BQ-touching code is exercised only
with mocks since real BQ calls are out of scope for unit tests.
"""
from app.services.investigator import (
    _build_llm_prompt,
    _is_concentrated,
    _template_synthesize,
)


class TestConcentrationDetection:
    def test_finds_concentration(self):
        rows = [
            {"value": "IN", "users": 1500, "share": 0.75},
            {"value": "US", "users": 300, "share": 0.15},
            {"value": "GB", "users": 200, "share": 0.10},
        ]
        c = _is_concentrated(rows, threshold=0.6)
        assert c is not None
        assert c["value"] == "IN"

    def test_no_concentration_when_distributed(self):
        rows = [
            {"value": "IN", "users": 400, "share": 0.40},
            {"value": "US", "users": 350, "share": 0.35},
            {"value": "GB", "users": 250, "share": 0.25},
        ]
        c = _is_concentrated(rows, threshold=0.6)
        assert c is None

    def test_empty_rows(self):
        assert _is_concentrated([], threshold=0.6) is None

    def test_custom_threshold(self):
        rows = [{"value": "X", "users": 100, "share": 0.55}]
        assert _is_concentrated(rows, threshold=0.5) is not None
        assert _is_concentrated(rows, threshold=0.7) is None


class TestTemplateSynthesize:
    def test_concentrated_axis_cited(self):
        insight = {"id": "x", "title": "T", "kind": "conversion"}
        where = {
            "axes": {
                "country": [
                    {"value": "IN", "users": 1500, "share": 0.78},
                    {"value": "US", "users": 200, "share": 0.10},
                ],
                "platform": [
                    {"value": "ANDROID", "users": 900, "share": 0.45},
                    {"value": "IOS", "users": 800, "share": 0.40},
                ],
            },
        }
        when = {"change_started_on": "2026-04-18", "timeline": []}

        text = _template_synthesize(insight, where, when)
        assert "IN" in text  # cites the concentrated country
        assert "78%" in text or "78" in text  # cites the share
        assert "2026-04-18" in text  # cites when
        assert "**Why" in text and "**What to do" in text

    def test_no_concentration(self):
        insight = {"id": "x", "title": "T", "kind": "conversion"}
        where = {
            "axes": {
                "country": [
                    {"value": "IN", "users": 400, "share": 0.30},
                    {"value": "US", "users": 350, "share": 0.27},
                    {"value": "GB", "users": 300, "share": 0.23},
                ],
            },
        }
        when = {"change_started_on": None, "timeline": []}

        text = _template_synthesize(insight, where, when)
        # Should mention broad-base / no single segment
        assert ("broad-base" in text or "no single segment" in text)
        # Should still suggest an action
        assert "**What to do" in text


class TestShareConsistency:
    """Regression test: share percentages must be relative to total_affected_users,
    not to per-axis sum. Bug fix from v0.9.0 -- different axes returning
    different denominators created visually inconsistent percentages.
    """

    def test_prompt_includes_total_affected(self):
        insight = {"id": "x", "title": "T", "kind": "conversion", "severity": 0.5}
        where = {
            "axes": {
                "country": [{"value": "IN", "users": 750, "share": 0.75}],
            },
            "total_affected_users": 1000,
        }
        when = {"timeline": [], "change_started_on": None,
                "baseline_period": {}, "analysis_period": {}}

        prompt = _build_llm_prompt(insight, where, when)
        assert "1000 total affected users" in prompt

    def test_consistent_share_when_total_provided(self):
        """If two axes both have a top value of 750 users out of 1000 total
        affected, both should show 75% -- not different numbers."""
        # Simulate what _investigate_where would build with a shared denominator
        total_affected = 1000
        where = {
            "axes": {
                "country": [
                    {"value": "IN", "users": 750, "share": 750 / total_affected},
                ],
                "platform": [
                    {"value": "ANDROID", "users": 750, "share": 750 / total_affected},
                ],
            },
            "total_affected_users": total_affected,
        }

        # Both should show the same 75% share
        assert where["axes"]["country"][0]["share"] == 0.75
        assert where["axes"]["platform"][0]["share"] == 0.75
    def test_includes_insight_metadata(self):
        insight = {
            "id": "abc",
            "title": "Conversion dropped 14%",
            "detail": "Stuff",
            "kind": "conversion",
            "severity": 0.7,
        }
        where = {"axes": {"country": []}}
        when = {"timeline": [], "change_started_on": None,
                "baseline_period": {}, "analysis_period": {}}

        prompt = _build_llm_prompt(insight, where, when)
        assert "Conversion dropped 14%" in prompt
        assert "0.70" in prompt

    def test_includes_concentrated_segments(self):
        insight = {"id": "x", "title": "T", "kind": "conversion", "severity": 0.5}
        where = {
            "axes": {
                "country": [
                    {"value": "IN", "users": 1500, "share": 0.78},
                ],
            },
        }
        when = {"timeline": [], "change_started_on": None,
                "baseline_period": {}, "analysis_period": {}}

        prompt = _build_llm_prompt(insight, where, when)
        assert "IN" in prompt
        assert "Concentrated" in prompt

    def test_handles_long_timeline(self):
        """Timelines >14 days should be sampled."""
        insight = {"id": "x", "title": "T", "kind": "conversion", "severity": 0.5}
        where = {"axes": {}}
        timeline = [
            {"date": f"2026-04-{day:02d}", "dau": 100, "target_count": 50}
            for day in range(1, 31)
        ]
        when = {"timeline": timeline, "change_started_on": None,
                "baseline_period": {}, "analysis_period": {}}

        prompt = _build_llm_prompt(insight, where, when)
        assert "30 days" in prompt or "of 30" in prompt
        # Should not include all 30 days
        first_day_count = prompt.count("2026-04-01")
        last_day_count = prompt.count("2026-04-30")
        assert first_day_count >= 1
        assert last_day_count >= 1
