"""Share token generation and access checks."""

from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import File, FileShare, Folder, FolderShare, User

TOKEN_BYTES = 24  # 48 hex chars, not guessable


def generate_token(db: Session) -> str:
    """A token has to be unique across both share tables, because a public link
    is resolved by token alone and only then discovers what it points at."""
    for _ in range(10):
        token = secrets.token_hex(TOKEN_BYTES)
        taken = db.execute(
            select(FileShare.id).where(FileShare.share_link == token)
        ).first() or db.execute(
            select(FolderShare.id).where(FolderShare.share_link == token)
        ).first()
        if taken is None:
            return token
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not allocate share token")


def get_share_by_token(db: Session, token: str) -> FileShare:
    share = db.execute(
        select(FileShare).where(FileShare.share_link == token)
    ).scalar_one_or_none()
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Share link not found")
    return share


def get_folder_share_by_token(db: Session, token: str) -> FolderShare:
    share = db.execute(
        select(FolderShare).where(FolderShare.share_link == token)
    ).scalar_one_or_none()
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Share link not found")
    return share


def resolve_token(db: Session, token: str) -> tuple[str, FileShare | FolderShare]:
    """Find whichever kind of share a public token belongs to."""
    file_share = db.execute(
        select(FileShare).where(FileShare.share_link == token)
    ).scalar_one_or_none()
    if file_share is not None:
        return "file", file_share

    folder_share = db.execute(
        select(FolderShare).where(FolderShare.share_link == token)
    ).scalar_one_or_none()
    if folder_share is not None:
        return "folder", folder_share

    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Share link not found")


def assert_usable(share: FileShare) -> File:
    """Validate expiry and that the underlying file still exists."""
    if share.expiry_date is not None and share.expiry_date < datetime.utcnow():
        raise HTTPException(status.HTTP_410_GONE, detail="This share link has expired")

    record = share.file
    if record is None or record.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="The shared file is no longer available")
    return record


def assert_folder_usable(share: FolderShare) -> Folder:
    """Validate expiry and that the shared folder still exists."""
    if share.expiry_date is not None and share.expiry_date < datetime.utcnow():
        raise HTTPException(status.HTTP_410_GONE, detail="This share link has expired")

    folder = share.folder
    if folder is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="The shared folder is no longer available"
        )
    return folder


def folders_shared_with(db: Session, user_id: int) -> list[int]:
    """Ids of every folder shared directly with this user, expiry respected."""
    shares = db.execute(
        select(FolderShare).where(FolderShare.shared_to == user_id)
    ).scalars().all()
    return [s.folder_id for s in shares if not s.is_expired]


def can_user_access(db: Session, user: User, record: File) -> bool:
    """True when the user owns the file, it was shared directly with them, or it
    sits inside a folder that was shared directly with them."""
    if record.user_id == user.id:
        return True

    share = db.execute(
        select(FileShare.id).where(
            FileShare.file_id == record.id, FileShare.shared_to == user.id
        )
    ).first()
    if share is not None:
        return True

    if record.folder_id is None:
        return False

    from app.services import folder_service

    for folder_id in folders_shared_with(db, user.id):
        owner_id = db.execute(
            select(Folder.user_id).where(Folder.id == folder_id)
        ).scalar_one_or_none()
        if owner_id is None:
            continue
        if record.folder_id in folder_service.descendant_ids(db, owner_id, folder_id):
            return True

    return False


def can_user_edit(db: Session, user: User, record: File) -> bool:
    """True if user owns the file or has editor permission through a share."""
    if record.user_id == user.id:
        return True

    # Check direct file share with editor permission
    share = db.execute(
        select(FileShare.permission).where(
            FileShare.file_id == record.id, FileShare.shared_to == user.id
        )
    ).scalar_one_or_none()
    if share == "editor":
        return True

    # Check folder shares with editor permission
    if record.folder_id is None:
        return False

    from app.services import folder_service

    for folder_id in folders_shared_with(db, user.id):
        owner_id = db.execute(
            select(Folder.user_id).where(Folder.id == folder_id)
        ).scalar_one_or_none()
        if owner_id is None:
            continue
        if record.folder_id in folder_service.descendant_ids(db, owner_id, folder_id):
            # Check if the folder share has editor permission
            folder_share = db.execute(
                select(FolderShare.permission).where(
                    FolderShare.folder_id == folder_id,
                    FolderShare.shared_to == user.id
                )
            ).scalar_one_or_none()
            if folder_share == "editor":
                return True

    return False


def public_url(request_base: str, token: str) -> str:
    return f"{request_base.rstrip('/')}/share.html?token={token}"
