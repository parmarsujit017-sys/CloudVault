"""Storage accounting.

Usage is always recomputed from the Files table so the Users and Storage rows
can never drift away from what is really on disk. Trashed files still count
against the quota (as in Google Drive) until permanently deleted.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import File, Storage, User
from app.utils.files import bytes_to_mb


def used_bytes(db: Session, user_id: int) -> int:
    total = db.execute(
        select(func.coalesce(func.sum(File.file_size), 0)).where(File.user_id == user_id)
    ).scalar_one()
    return int(total or 0)


def sync_user_storage(db: Session, user: User) -> Storage:
    """Recalculate storage from real files and mirror it into both tables."""
    used_mb = bytes_to_mb(used_bytes(db, user.id))
    limit_mb = float(user.storage_limit or settings.DEFAULT_STORAGE_LIMIT_MB)

    user.storage_used = used_mb

    row = db.execute(select(Storage).where(Storage.user_id == user.id)).scalar_one_or_none()
    if row is None:
        row = Storage(user_id=user.id)
        db.add(row)

    row.total_storage = limit_mb
    row.used_storage = used_mb
    row.available_storage = max(limit_mb - used_mb, 0.0)

    db.flush()
    return row


def has_room_for(db: Session, user: User, incoming_bytes: int) -> bool:
    limit_bytes = float(user.storage_limit or 0) * 1024 * 1024
    return (used_bytes(db, user.id) + incoming_bytes) <= limit_bytes


def remaining_bytes(db: Session, user: User) -> int:
    limit_bytes = int(float(user.storage_limit or 0) * 1024 * 1024)
    return max(limit_bytes - used_bytes(db, user.id), 0)
