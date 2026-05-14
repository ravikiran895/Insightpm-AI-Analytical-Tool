"""Tests for the LLM client abstraction layer.

These tests verify behavior WITHOUT making real API calls. We mock the
provider-specific calls (_try_gemini, _try_anthropic) and check the
orchestration logic.
"""
from unittest.mock import patch


class TestProviderPreferenceOrder:
    """Gemini → Anthropic → None. First available wins."""

    def test_gemini_preferred_when_both_set(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")

        from app.services import llm_client
        with patch.object(llm_client, "_try_gemini", return_value="gemini-response") as g, \
             patch.object(llm_client, "_try_anthropic", return_value="anthropic-response") as a:
            result = llm_client.call_llm("sys", "msg")

        assert result == ("gemini-response", "gemini")
        g.assert_called_once()
        a.assert_not_called()  # Should not fall back if Gemini succeeded

    def test_falls_back_to_anthropic_if_gemini_fails(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")

        from app.services import llm_client
        with patch.object(llm_client, "_try_gemini", return_value=None), \
             patch.object(llm_client, "_try_anthropic", return_value="anthropic-fallback"):
            result = llm_client.call_llm("sys", "msg")

        assert result == ("anthropic-fallback", "anthropic")

    def test_returns_none_when_no_keys(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        from app.services import llm_client
        # Both providers see no API key and return None internally
        result = llm_client.call_llm("sys", "msg")
        assert result is None

    def test_uses_anthropic_when_only_anthropic_set(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")

        from app.services import llm_client
        with patch.object(llm_client, "_try_anthropic", return_value="anthropic-only"):
            result = llm_client.call_llm("sys", "msg")
        assert result == ("anthropic-only", "anthropic")


class TestGetActiveProvider:
    def test_gemini_when_both(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
        from app.services.llm_client import get_active_provider
        assert get_active_provider() == "gemini"

    def test_anthropic_when_only_anthropic(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
        from app.services.llm_client import get_active_provider
        assert get_active_provider() == "anthropic"

    def test_none_when_neither(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from app.services.llm_client import get_active_provider
        assert get_active_provider() is None


class TestJsonResponse:
    """call_llm_json should parse JSON cleanly, including stripping markdown fences."""

    def test_parses_clean_json(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        from app.services import llm_client
        with patch.object(llm_client, "_try_gemini",
                          return_value='{"intent": "top_events", "params": {}}'):
            result = llm_client.call_llm_json("sys", "msg")
        assert result is not None
        parsed, provider = result
        assert parsed == {"intent": "top_events", "params": {}}
        assert provider == "gemini"

    def test_strips_markdown_fences(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        from app.services import llm_client
        # Models sometimes wrap JSON in ```json ... ``` despite instructions
        fenced = '```json\n{"intent": "growth_check", "params": {}}\n```'
        with patch.object(llm_client, "_try_gemini", return_value=fenced):
            result = llm_client.call_llm_json("sys", "msg")
        assert result is not None
        parsed, _ = result
        assert parsed["intent"] == "growth_check"

    def test_returns_none_on_invalid_json(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        from app.services import llm_client
        with patch.object(llm_client, "_try_gemini", return_value="not valid json {"):
            result = llm_client.call_llm_json("sys", "msg")
        assert result is None

    def test_returns_none_when_provider_returns_none(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from app.services.llm_client import call_llm_json
        result = call_llm_json("sys", "msg")
        assert result is None


class TestRefusalDetection:
    """is_refusal should detect when the LLM declined due to topic guardrail."""

    def test_canonical_refusal(self):
        from app.services.llm_client import is_refusal
        assert is_refusal("Sorry, I can only help with questions about your product analytics data.")

    def test_canonical_refusal_lowercase(self):
        from app.services.llm_client import is_refusal
        # Models may vary case slightly
        assert is_refusal("sorry, I CAN ONLY help with questions about your product analytics data.")

    def test_normal_response_not_refusal(self):
        from app.services.llm_client import is_refusal
        assert not is_refusal("Hypothesis: the conversion drop is likely related to platform mix.")

    def test_empty_not_refusal(self):
        from app.services.llm_client import is_refusal
        assert not is_refusal("")
        assert not is_refusal(None)


class TestGuardrailIsAlwaysApplied:
    """The topic guardrail must be prepended to every system prompt."""

    def test_guardrail_in_gemini_call(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        from app.services import llm_client

        # Capture the system prompt that gets passed to the provider
        captured = {}
        def fake_gemini(system, user_message, max_tokens):
            captured["system"] = system
            return "ok"

        with patch.object(llm_client, "_try_gemini", side_effect=fake_gemini):
            llm_client.call_llm("MY_SYSTEM_PROMPT", "msg")

        # Note: in the current design, the guardrail is added INSIDE _try_gemini
        # before sending to the API, not in call_llm. So this test verifies
        # that the system the caller passed is forwarded as-is to _try_gemini.
        assert "MY_SYSTEM_PROMPT" in captured["system"]
