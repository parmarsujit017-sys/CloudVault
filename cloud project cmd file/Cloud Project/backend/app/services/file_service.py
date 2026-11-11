"""File ownership, upload and trash helpers."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta
from itertools import islice
from typing import BinaryIO

from docx import Document as WordDocument
from openpyxl import Workbook

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import File, FileShare, Trash, User
from app.services import activity_service, folder_service, storage_service
from app.services.storage_backend import LocalStorageBackend, storage_backend
from app.utils.files import (
    bytes_to_mb,
    generate_stored_name,
    guess_mime,
    is_blocked,
    sanitize_display_name,
)


def get_owned_file(db: Session, user: User, file_id: int, include_trashed: bool = False) -> File:
    """Fetch a file the caller actually owns. 404 unknown, 403 someone else's."""
    record = db.get(File, file_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
    if record.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have access to this file")
    if record.is_deleted and not include_trashed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File is in the trash")
    return record


def _docx_bytes_for_content(content: str) -> bytes:
    doc = WordDocument()
    if content:
        try:
            doc.add_paragraph(content)
        except Exception:
            doc.add_paragraph(content or "")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _xlsx_bytes_for_data(data: dict | None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    rows = ((data or {}).get("sheets") or [{}])[0].get("data") or []
    for row in rows:
        sheet.append([cell for cell in row])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def create_document_file(db: Session, user: User, name: str, kind: str, folder_id: int | None = None) -> File:
    allowed = {"word", "excel"}
    if kind not in allowed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="File type must be 'word' or 'excel'")

    clean_name = sanitize_display_name(name)
    if not clean_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="File name is required")
    suffix = ".docx" if kind == "word" else ".xlsx"
    original_name = clean_name if clean_name.lower().endswith(suffix) else f"{clean_name}{suffix}"
    original_name = unique_file_name(db, user.id, folder_id, original_name)

    stored_name = generate_stored_name(original_name)
    relative_path = LocalStorageBackend.build_path(user.id, stored_name)

    if kind == "word":
        payload = ""
        file_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        content = payload
        binary = _docx_bytes_for_content(content)
    else:
        payload = {"sheets": [{"name": "Sheet1", "data": [["A1", "B1"]]}]}
        file_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        content = json.dumps(payload)
        binary = _xlsx_bytes_for_data(payload)

    size = storage_backend.save(relative_path, io.BytesIO(binary), len(binary))
    record = File(
        user_id=user.id,
        folder_id=folder_id,
        file_name=stored_name,
        original_name=original_name,
        kind=kind,
        file_type=file_type,
        file_size=size,
        file_path=relative_path,
        document_content=content if kind == "word" else None,
        spreadsheet_data=payload if kind == "excel" else None,
    )
    db.add(record)
    db.flush()
    storage_service.sync_user_storage(db, user)
    return record


def sync_document_bytes(record: File) -> None:
    if record.kind == "word":
        payload = record.document_content or ""
        binary = _docx_bytes_for_content(payload)
    elif record.kind == "excel":
        payload = record.spreadsheet_data or {"sheets": [{"name": "Sheet1", "data": []}]}
        binary = _xlsx_bytes_for_data(payload)
    else:
        return

    if record.file_path:
        try:
            storage_backend.delete(record.file_path)
        except Exception:
            pass
        stream = io.BytesIO(binary)
        record.file_size = storage_backend.save(record.file_path, stream, len(binary))
        record.file_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if record.kind == "word"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


def store_upload(
    db: Session,
    user: User,
    upload_stream: BinaryIO,
    original_filename: str,
    content_type: str | None,
    folder_id: int | None,
    ip_address: str | None = None,
) -> File:
    """Validate, write to storage and record a single uploaded file."""
    original = sanitize_display_name(original_filename)

    if is_blocked(original):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Files of type {original.rsplit('.', 1)[-1]} are not allowed",
        )

    quota_left = storage_service.remaining_bytes(db, user)
    cap = min(settings.max_file_size_bytes, quota_left) if quota_left else 0
    if cap <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Storage limit exceeded")

    stored_name = generate_stored_name(original)
    relative_path = LocalStorageBackend.build_path(user.id, stored_name)

    try:
        size = storage_backend.save(relative_path, upload_stream, cap)
    except ValueError:
        storage_backend.delete(relative_path)
        if quota_left < settings.max_file_size_bytes:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Storage limit exceeded")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds the {settings.MAX_FILE_SIZE_MB} MB upload limit",
        )

    record = File(
        user_id=user.id,
        folder_id=folder_id,
        file_name=stored_name,
        original_name=original,
        file_type=guess_mime(original, content_type),
        file_size=size,
        file_path=relative_path,
    )
    db.add(record)
    db.flush()

    storage_service.sync_user_storage(db, user)
    activity_service.log(db, user.id, activity_service.UPLOAD, original, ip_address)
    return record


def unique_file_name(
    db: Session, user_id: int, folder_id: int | None, name: str, marker: str | None = "copy"
) -> str:
    """A name no other live file in this folder is using.

    The suffix lands before the extension - `report (copy).pdf`, not
    `report.pdf (copy)` - so the file still opens in the right application.
    """
    def taken(candidate: str) -> bool:
        return db.execute(
            select(File.id).where(
                File.user_id == user_id,
                File.folder_id.is_(None) if folder_id is None else File.folder_id == folder_id,
                File.is_deleted.is_(False),
                func.lower(File.original_name) == candidate.lower(),
            )
        ).first() is not None

    if not taken(name):
        return name

    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    suffix = f".{ext}" if dot else ""

    for variant in islice(folder_service.name_variants(stem, marker), 500):
        if not taken(variant + suffix):
            return variant + suffix

    raise HTTPException(
        status.HTTP_409_CONFLICT, detail="Too many files here share that name"
    )


def copy_file(
    db: Session,
    user: User,
    record: File,
    folder_id: int | None,
    rename_on_clash: bool = True,
    ip_address: str | None = None,
) -> File:
    """Duplicate a file, bytes and all, into `folder_id`.

    The copy gets its own stored name so deleting either side never disturbs the
    other, and it is charged against the quota exactly like a fresh upload.
    """
    if not storage_backend.exists(record.file_path):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"'{record.original_name}' is missing from storage and cannot be copied",
        )

    quota_left = storage_service.remaining_bytes(db, user)
    if record.file_size > quota_left:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Storage limit exceeded")

    name = record.original_name
    if rename_on_clash:
        name = unique_file_name(db, user.id, folder_id, name)

    stored_name = generate_stored_name(name)
    relative_path = LocalStorageBackend.build_path(user.id, stored_name)

    try:
        with storage_backend.open(record.file_path) as source:
            size = storage_backend.save(relative_path, source, quota_left)
    except ValueError:
        storage_backend.delete(relative_path)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Storage limit exceeded")
    except OSError:
        storage_backend.delete(relative_path)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not copy '{record.original_name}'"
        )

    duplicate = File(
        user_id=user.id,
        folder_id=folder_id,
        file_name=stored_name,
        original_name=name,
        file_type=record.file_type,
        file_size=size,
        file_path=relative_path,
    )
    db.add(duplicate)
    db.flush()

    storage_service.sync_user_storage(db, user)
    if ip_address is not None:
        activity_service.log(db, user.id, activity_service.COPY_FILE, name, ip_address)
    return duplicate


def move_to_trash(db: Session, user: User, record: File, ip_address: str | None = None) -> Trash:
    """Soft delete: hide the file and schedule it for automatic purge."""
    record.is_deleted = True
    record.updated_at = datetime.utcnow()

    entry = db.execute(select(Trash).where(Trash.file_id == record.id)).scalar_one_or_none()
    now = datetime.utcnow()
    auto_delete = now + timedelta(days=settings.TRASH_RETENTION_DAYS)
    if entry is None:
        entry = Trash(file_id=record.id, user_id=user.id, deleted_at=now, auto_delete=auto_delete)
        db.add(entry)
    else:
        entry.deleted_at = now
        entry.auto_delete = auto_delete

    db.flush()
    storage_service.sync_user_storage(db, user)
    activity_service.log(db, user.id, activity_service.DELETE_FILE, record.original_name, ip_address)
    return entry


def restore(db: Session, user: User, record: File, ip_address: str | None = None) -> File:
    record.is_deleted = False
    record.updated_at = datetime.utcnow()

    entry = db.execute(select(Trash).where(Trash.file_id == record.id)).scalar_one_or_none()
    if entry is not None:
        db.delete(entry)

    db.flush()
    storage_service.sync_user_storage(db, user)
    activity_service.log(db, user.id, activity_service.RESTORE_FILE, record.original_name, ip_address)
    return record


def purge(db: Session, user: User, record: File, ip_address: str | None = None) -> None:
    """Permanently remove the DB rows, the shares and the bytes on disk."""
    name = record.original_name
    path = record.file_path

    db.execute(select(FileShare).where(FileShare.file_id == record.id))
    for share in list(record.shares):
        db.delete(share)
    if record.trash is not None:
        db.delete(record.trash)
    db.delete(record)
    db.flush()

    storage_backend.delete(path)
    storage_service.sync_user_storage(db, user)
    activity_service.log(db, user.id, activity_service.PERMANENT_DELETE, name, ip_address)


def purge_expired_trash(db: Session) -> int:
    """Delete trashed files whose auto_delete date has passed."""
    now = datetime.utcnow()
    entries = db.execute(select(Trash).where(Trash.auto_delete <= now)).scalars().all()
    removed = 0
    for entry in entries:
        record = db.get(File, entry.file_id)
        owner = db.get(User, entry.user_id)
        if record is None or owner is None:
            db.delete(entry)
            continue
        purge(db, owner, record)
        removed += 1
    if entries:
        db.commit()
    return removed


def to_dict(record: File) -> dict:
    return {
        "id": record.id,
        "folder_id": record.folder_id,
        "file_name": record.file_name,
        "original_name": record.original_name,
        "file_type": record.file_type,
        "file_size": record.file_size,
        "size_mb": bytes_to_mb(record.file_size),
        "uploaded_at": record.uploaded_at,
        "updated_at": record.updated_at,
        "is_starred": record.is_starred,
    }
