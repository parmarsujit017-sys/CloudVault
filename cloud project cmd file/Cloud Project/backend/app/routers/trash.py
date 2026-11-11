"""Trash: list, restore, permanently delete, empty."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import client_ip, get_current_user
from app.database import get_db
from app.models import File, Trash, User
from app.schemas.common import Message
from app.schemas.file import TrashOut
from app.services import file_service

router = APIRouter(prefix="/api/trash", tags=["trash"])


@router.get("", response_model=list[TrashOut], summary="List the current user's Trash")
def list_trash(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Trash, File)
        .join(File, File.id == Trash.file_id)
        .where(Trash.user_id == user.id)
        .order_by(Trash.deleted_at.desc())
    ).all()

    return [
        TrashOut(
            id=entry.id,
            file_id=record.id,
            original_name=record.original_name,
            file_type=record.file_type,
            file_size=record.file_size,
            deleted_at=entry.deleted_at,
            auto_delete=entry.auto_delete,
        )
        for entry, record in rows
    ]


@router.post("/{file_id}/restore", response_model=Message, summary="Restore a file from Trash")
def restore_file(
    file_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = file_service.get_owned_file(db, user, file_id, include_trashed=True)
    name = record.original_name
    file_service.restore(db, user, record, client_ip(request))
    db.commit()
    return Message(message=f"'{name}' restored")


@router.delete("/{file_id}", response_model=Message, summary="Permanently delete one file")
def permanent_delete(
    file_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = file_service.get_owned_file(db, user, file_id, include_trashed=True)
    name = record.original_name
    file_service.purge(db, user, record, client_ip(request))
    db.commit()
    return Message(message=f"'{name}' permanently deleted")


@router.delete("", response_model=Message, summary="Empty the Trash")
def empty_trash(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entries = db.execute(select(Trash).where(Trash.user_id == user.id)).scalars().all()
    count = 0
    for entry in entries:
        record = db.get(File, entry.file_id)
        if record is None:
            db.delete(entry)
            continue
        file_service.purge(db, user, record, client_ip(request))
        count += 1
    db.commit()
    return Message(message=f"{count} file(s) permanently deleted")
