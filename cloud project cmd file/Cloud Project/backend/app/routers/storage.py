"""Storage metrics, always derived from the real Files table."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.dashboard import StorageOut
from app.services import storage_service

router = APIRouter(prefix="/api/storage", tags=["storage"])


@router.get("", response_model=StorageOut, summary="Current storage usage in MB")
def get_storage(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = storage_service.sync_user_storage(db, user)
    db.commit()

    percent = (row.used_storage / row.total_storage * 100) if row.total_storage else 0.0

    # 4 decimal places of a megabyte is ~100 bytes, so small files still show
    # up in the UI instead of rounding away to "0 B".
    return StorageOut(
        total_storage=round(row.total_storage, 4),
        used_storage=round(row.used_storage, 4),
        available_storage=round(row.available_storage, 4),
        used_percent=round(percent, 2),
    )
