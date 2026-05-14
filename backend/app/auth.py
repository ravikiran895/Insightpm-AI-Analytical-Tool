"""
Simple shared-password authentication.

Why "simple": this is a single-tenant tool where the team trust model is
"everyone with the link knows the password." Not designed for adversarial
multi-user setups; designed to keep accidental discovery of your localhost
or LAN-exposed instance from leaking your data.

Activation: set INSIGHTPM_PASSWORD in .env. If unset, auth is OFF and the
app behaves exactly like before -- this preserves the local-dev experience.

Wire model:
- Frontend sends X-InsightPM-Auth header with each /api/* call.
- The header value is the SHA-256 hex digest of the password.
- We never accept the plain password over the wire, even though /api is
  typically localhost. This means a screen-share or console screenshot
  doesn't expose the password.
- The frontend stores the digest in sessionStorage (cleared on tab close).

Endpoints exempted from auth:
- /api/auth/check  (the login endpoint itself)
- /api/auth/status (tells the frontend whether auth is enabled)

CSRF: not relevant -- we don't use cookies. The header must be set
explicitly by JS, so cross-origin requests from another site can't trigger
authenticated calls.
"""
from __future__ import annotations

import hashlib
import hmac
import os


_HEADER_NAME = "x-insightpm-auth"

# Endpoints that don't require auth. Keep this list minimal.
_PUBLIC_PATHS = {
    "/api/auth/check",
    "/api/auth/status",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _expected_digest() -> str | None:
    """Returns the SHA-256 digest the frontend should send, or None if
    auth is disabled."""
    pwd = os.getenv("INSIGHTPM_PASSWORD")
    if not pwd:
        return None
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()


def is_auth_enabled() -> bool:
    return _expected_digest() is not None


async def auth_middleware(request, call_next):
    """FastAPI HTTP middleware. Checks the auth header on /api/* paths.

    The `request` parameter is a fastapi.Request -- typed loosely here so
    this module is importable in unit tests without fastapi installed.
    The middleware function itself is only ever called by FastAPI."""
    path = request.url.path

    # Always allow public paths
    if path in _PUBLIC_PATHS:
        return await call_next(request)

    # Only protect /api/* routes
    if not path.startswith("/api/"):
        return await call_next(request)

    expected = _expected_digest()
    if expected is None:
        # Auth disabled -- pass through unchanged
        return await call_next(request)

    # Compare digests in constant time
    provided = request.headers.get(_HEADER_NAME, "")
    if not hmac.compare_digest(provided, expected):
        # Lazy-import here so the module is testable without fastapi
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required. Set X-InsightPM-Auth header."},
        )

    return await call_next(request)


def verify_password_for_login(password: str) -> bool:
    """Used by the /auth/check endpoint. Returns True if the password matches."""
    expected_pwd = os.getenv("INSIGHTPM_PASSWORD")
    if not expected_pwd:
        return False
    return hmac.compare_digest(password, expected_pwd)
