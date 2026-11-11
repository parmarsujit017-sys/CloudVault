"""Activity log access for the current user, and system-wide for admins."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_admin, get_current_user
from app.database import get_db
from app.models import ActivityLog, User
from app.schemas.file import ActivityOut, ActivityWithUser
from app.schemas.user import UserBrief

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("", response_model=list[ActivityOut], summary="The current user's activity")
def my_activity(
    limit: int = Query(default=50, le=200),
    activity: str | None = Query(default=None, description="Filter by activity type"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(ActivityLog).where(ActivityLog.user_id == user.id)
    if activity:
        stmt = stmt.where(ActivityLog.activity == activity.upper())
    return db.execute(
        stmt.order_by(ActivityLog.activity_time.desc(), ActivityLog.id.desc()).limit(limit)
    ).scalars().all()


@router.get("/all", response_model=list[ActivityWithUser], summary="System activity (admin only)")
def all_activity(
    limit: int = Query(default=100, le=500),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(ActivityLog)
        .order_by(ActivityLog.activity_time.desc(), ActivityLog.id.desc())
        .limit(limit)
    ).scalars().all()

    out: list[ActivityWithUser] = []
    for row in rows:
        item = ActivityWithUser.model_validate(row)
        item.user = UserBrief.model_validate(row.user) if row.user else None
        out.append(item)
    return out
