"""Auth check + status endpoints. Only two endpoints; these are the
ONLY routes exempted from the password gate (because the frontend uses
them to figure out whether/how to gate itself)."""
import hashlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..auth import is_auth_enabled, verify_password_for_login

router = APIRouter()


class AuthCheckRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)


@router.get("/auth/status")
def auth_status():
    """Tells the frontend whether auth is enabled. Always public."""
    return {"enabled": is_auth_enabled()}


@router.post("/auth/check")
def auth_check(req: AuthCheckRequest):
    """Verify the user's password. Returns the digest the frontend needs
    to send with subsequent API calls.

    We return the digest (not a session token) because:
    - It's deterministic from the password, so server restarts don't log
      everyone out.
    - It's not a useful credential elsewhere (only matches one specific
      password on one specific server).
    - Simpler than session management for a single-tenant tool.
    """
    if not is_auth_enabled():
        # No password configured server-side -- return success but with
        # no digest. Frontend will detect this and not send a header.
        return {"ok": True, "digest": None, "auth_enabled": False}

    if not verify_password_for_login(req.password):
        raise HTTPException(status_code=401, detail="Wrong password.")

    digest = hashlib.sha256(req.password.encode("utf-8")).hexdigest()
    return {"ok": True, "digest": digest, "auth_enabled": True}
