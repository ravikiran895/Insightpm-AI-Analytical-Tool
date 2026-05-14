"""User Behavior Profiler endpoints — the headline USP feature."""
from fastapi import APIRouter, Query

from ..models.schemas import UserProfileRequest
from ..services import user_profiler

router = APIRouter()


@router.post("/users/profile")
def profile_user(req: UserProfileRequest):
    return user_profiler.profile_user(
        user_id=req.user_id,
        start_date=req.start_date,
        end_date=req.end_date,
    )


@router.get("/users/recent")
def recent_users(
    start_date: str = Query(..., pattern=r"^\d{8}$"),
    end_date: str = Query(..., pattern=r"^\d{8}$"),
    limit: int = Query(20, ge=1, le=50),
):
    """Lightweight endpoint to populate the user-picker UI with examples."""
    return {"users": user_profiler.find_recent_users(start_date, end_date, limit)}
