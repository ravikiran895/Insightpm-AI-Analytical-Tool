"""
FastAPI entrypoint.

Run with: uvicorn app.main:app --reload --port 8000
"""
import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import auth_middleware, is_auth_enabled
from .config import frontend_origin
from .logging_setup import setup_logging
from .routers import (
    auth as auth_router,
    breakdown,
    connection,
    dashboard,
    events,
    funnel,
    insights,
    nlq,
    retention,
    saved_cohorts,
    saved_funnels,
    sql_preview,
    system,
    user_profile,
)

# Initialize logging before anything else logs.
setup_logging()
log = logging.getLogger("insightpm")

app = FastAPI(title="InsightPM API", version="0.9.2")

# CORS first
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-InsightPM-Auth"],
)

# Auth middleware (no-op if INSIGHTPM_PASSWORD not set in .env)
app.middleware("http")(auth_middleware)


@app.on_event("startup")
def _on_startup():
    """Initialize SQLite, load default profile if any, otherwise fall back to env."""
    from .config import initialize_active_config
    initialize_active_config()
    if is_auth_enabled():
        log.info("InsightPM started -- auth ENABLED (INSIGHTPM_PASSWORD set)")
    else:
        log.info("InsightPM started -- auth disabled (no password configured)")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Convert raw Python exceptions into structured JSON the frontend can render."""
    error_message = str(exc)
    error_kind = "internal_error"

    msg_lower = error_message.lower()
    if "not found" in msg_lower and ("dataset" in msg_lower or "table" in msg_lower):
        error_kind = "not_found"
        error_message = (
            f"BigQuery dataset or table not found. Check your project_id and "
            f"dataset_id in the connection screen. Original: {error_message}"
        )
    elif "permission denied" in msg_lower or "access denied" in msg_lower or "forbidden" in msg_lower:
        error_kind = "permission_denied"
        error_message = (
            f"Permission denied. Make sure your service account has "
            f"'BigQuery Data Viewer' and 'BigQuery Job User' roles on the project. "
            f"Original: {error_message}"
        )
    elif "quota" in msg_lower or "rate limit" in msg_lower:
        error_kind = "quota_exceeded"
        error_message = f"BigQuery quota or rate limit hit. Original: {error_message}"

    log.error(f"Unhandled exception on {request.url.path}:\n{traceback.format_exc()}")

    return JSONResponse(
        status_code=500,
        content={
            "detail": error_message,
            "kind": error_kind,
            "path": str(request.url.path),
        },
    )


API = "/api"
app.include_router(auth_router.router, prefix=API, tags=["auth"])
app.include_router(connection.router, prefix=API, tags=["connection"])
app.include_router(events.router, prefix=API, tags=["events"])
app.include_router(funnel.router, prefix=API, tags=["funnel"])
app.include_router(retention.router, prefix=API, tags=["retention"])
app.include_router(insights.router, prefix=API, tags=["insights"])
app.include_router(nlq.router, prefix=API, tags=["nlq"])
app.include_router(system.router, prefix=API, tags=["system"])
app.include_router(sql_preview.router, prefix=API, tags=["sql"])
app.include_router(saved_funnels.router, prefix=API, tags=["saved_funnels"])
app.include_router(saved_cohorts.router, prefix=API, tags=["saved_cohorts"])
app.include_router(breakdown.router, prefix=API, tags=["breakdown"])
app.include_router(user_profile.router, prefix=API, tags=["user_profile"])
app.include_router(dashboard.router, prefix=API, tags=["dashboard"])


@app.get("/health")
def health():
    return {"ok": True}
