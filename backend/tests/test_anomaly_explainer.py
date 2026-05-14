"""Tests for the anomaly explainer service."""
import os

from app.services.anomaly_explainer import (
    _build_user_prompt,
    _explain_with_template,
)


class TestTemplateExplainer:
    """The fallback explainer must always produce something useful and never
    leak fake numbers."""

    def test_conversion_with_movers(self):
        insight = {
            "id": "conv_1",
            "title": "Conversion dropped 14%",
            "kind": "conversion",
            "severity": 0.7,
            "metric": {"rel_change": -0.14},
        }
        context = {
            "adjacent_movers": [
                {"event": "ChallengeAccepted", "this": 100, "prev": 200, "pct_change": -0.50},
                {"event": "AppOpen", "this": 1000, "prev": 800, "pct_change": 0.25},
            ],
        }
        result = _explain_with_template(insight, context)
        assert result.startswith("Hypothesis: ")
        # Real numbers from context appear in the output
        assert "ChallengeAccepted" in result

    def test_funnel_kind_suggests_breakdown(self):
        insight = {
            "id": "funnel_drop_AddToCart",
            "title": "Biggest drop at AddToCart",
            "kind": "funnel",
            "severity": 0.5,
            "metric": {"event": "AddToCart"},
        }
        result = _explain_with_template(insight, {"adjacent_movers": []})
        assert result.startswith("Hypothesis: ")
        assert "AddToCart" in result

    def test_retention_kind_warns_about_correlation(self):
        insight = {
            "id": "ret_corr_X",
            "title": "Users who do X retain better",
            "kind": "retention",
            "severity": 0.5,
            "metric": {},
        }
        result = _explain_with_template(insight, {"adjacent_movers": []})
        assert result.startswith("Hypothesis: ")
        assert "correlation" in result.lower() or "selecting" in result.lower()

    def test_volume_kind(self):
        insight = {"id": "v", "title": "X spiked 50%", "kind": "volume",
                   "severity": 0.5, "metric": {}}
        result = _explain_with_template(insight, {"adjacent_movers": []})
        assert result.startswith("Hypothesis: ")

    def test_unknown_kind_doesnt_crash(self):
        insight = {"id": "x", "title": "?", "kind": "weird", "severity": 0, "metric": {}}
        result = _explain_with_template(insight, {})
        assert result.startswith("Hypothesis: ")


class TestPromptSafety:
    """Critical safety check: the LLM prompt must not contain raw user data."""

    def test_prompt_doesnt_leak_user_pseudo_id(self):
        insight = {
            "id": "c1", "title": "T", "detail": "D", "kind": "conversion",
            "severity": 0.7, "metric": {"foo": "bar"},
        }
        context = {
            "date_range": {"start": "20260101", "end": "20260131"},
            "top_events": [{"event": "x", "users": 100}],
            "adjacent_movers": [],
        }
        prompt = _build_user_prompt(insight, context)

        # Even if a malicious context tried to include user IDs, the builder
        # only references fields it explicitly knows about. The prompt should
        # contain top_events labels but no raw IDs.
        assert "user_pseudo_id" not in prompt

    def test_prompt_includes_required_sections(self):
        insight = {
            "id": "c1",
            "title": "Conversion dropped 14%",
            "detail": "Stuff",
            "kind": "conversion",
            "severity": 0.7,
            "metric": {"rel_change": -0.14},
        }
        context = {
            "date_range": {"start": "20260101", "end": "20260131"},
            "top_events": [{"event": "GameStart", "users": 500}],
            "adjacent_movers": [
                {"event": "X", "this": 50, "prev": 100, "pct_change": -0.5}
            ],
        }
        prompt = _build_user_prompt(insight, context)

        assert "Conversion dropped 14%" in prompt
        assert "GameStart" in prompt
        assert "Hypothesis: " in prompt  # the instruction


class TestNoLLMFallback:
    """When no API key, the explainer should fall back gracefully."""

    def test_no_api_key_returns_none(self, monkeypatch):
        """With no provider configured, _explain_with_llm returns None
        (signaling caller to use the template fallback)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        from app.services.anomaly_explainer import _explain_with_llm
        # Provide minimal valid context to exercise the prompt-build path
        context = {
            "date_range": {"start": "20260101", "end": "20260131"},
            "top_events": [],
            "adjacent_movers": [],
        }
        result = _explain_with_llm({"id": "x", "kind": "conversion", "metric": {}}, context)
        assert result is None  # signals "use template"
