"""Auth middleware + endpoint tests."""
import hashlib


class TestAuthHelpers:
    def test_disabled_when_no_password(self, monkeypatch):
        monkeypatch.delenv("INSIGHTPM_PASSWORD", raising=False)
        from app.auth import is_auth_enabled, _expected_digest
        assert is_auth_enabled() is False
        assert _expected_digest() is None

    def test_enabled_when_password_set(self, monkeypatch):
        monkeypatch.setenv("INSIGHTPM_PASSWORD", "secret123")
        from app.auth import is_auth_enabled, _expected_digest
        assert is_auth_enabled() is True
        expected = hashlib.sha256(b"secret123").hexdigest()
        assert _expected_digest() == expected

    def test_verify_password_correct(self, monkeypatch):
        monkeypatch.setenv("INSIGHTPM_PASSWORD", "mypass")
        from app.auth import verify_password_for_login
        assert verify_password_for_login("mypass") is True

    def test_verify_password_wrong(self, monkeypatch):
        monkeypatch.setenv("INSIGHTPM_PASSWORD", "mypass")
        from app.auth import verify_password_for_login
        assert verify_password_for_login("wrong") is False
        assert verify_password_for_login("") is False

    def test_verify_password_when_disabled(self, monkeypatch):
        monkeypatch.delenv("INSIGHTPM_PASSWORD", raising=False)
        from app.auth import verify_password_for_login
        # If auth isn't configured, no password should validate
        assert verify_password_for_login("anything") is False

    def test_constant_time_comparison(self, monkeypatch):
        """The verify function should use hmac.compare_digest -- a smoke
        test that very-different and just-slightly-wrong both return False
        without leaking timing info would require tooling we don't have,
        so we just test the API returns the right boolean."""
        monkeypatch.setenv("INSIGHTPM_PASSWORD", "abc123")
        from app.auth import verify_password_for_login
        assert verify_password_for_login("abc123") is True
        assert verify_password_for_login("abc124") is False
        assert verify_password_for_login("xyz999") is False
