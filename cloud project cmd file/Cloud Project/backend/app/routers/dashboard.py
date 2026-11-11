"""Aggregated dashboard counters, all computed from live data."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import ActivityLog, File, FileShare, Folder, FolderShare, Trash, User
from app.schemas.dashboard import DashboardOut
from app.services import storage_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut, summary="Dashboard statistics")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = storage_service.sync_user_storage(db, user)
    db.commit()

    total_files = db.execute(
        select(func.count(File.id)).where(File.user_id == user.id, File.is_deleted.is_(False))
    ).scalar_one()

    total_folders = db.execute(
        select(func.count(Folder.id)).where(Folder.user_id == user.id)
    ).scalar_one()

    trash_files = db.execute(
        select(func.count(Trash.id)).where(Trash.user_id == user.id)
    ).scalar_one()

    # Counts everything "Shared with me" actually lists, folders included, so
    # the sidebar badge cannot disagree with the page it points at.
    shared_files = db.execute(
        select(func.count(FileShare.id))
        .join(File, File.id == FileShare.file_id)
        .where(FileShare.shared_to == user.id, File.is_deleted.is_(False))
    ).scalar_one() + db.execute(
        select(func.count(FolderShare.id))
        .join(Folder, Folder.id == FolderShare.folder_id)
        .where(FolderShare.shared_to == user.id)
    ).scalar_one()

    recent_files = db.execute(
        select(File)
        .where(File.user_id == user.id, File.is_deleted.is_(False))
        .order_by(File.updated_at.desc())
        .limit(8)
    ).scalars().all()

    recent_activity = db.execute(
        select(ActivityLog)
        .where(ActivityLog.user_id == user.id)
        .order_by(ActivityLog.activity_time.desc(), ActivityLog.id.desc())
        .limit(8)
    ).scalars().all()

    percent = (row.used_storage / row.total_storage * 100) if row.total_storage else 0.0

    return DashboardOut(
        total_files=total_files,
        total_folders=total_folders,
        storage_used=round(row.used_storage, 4),
        storage_limit=round(row.total_storage, 4),
        available_storage=round(row.available_storage, 4),
        used_percent=round(percent, 2),
        shared_files=shared_files,
        trash_files=trash_files,
        recent_files=recent_files,
        recent_activity=recent_activity,
    )
