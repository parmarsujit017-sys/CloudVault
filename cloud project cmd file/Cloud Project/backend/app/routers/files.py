"""File upload, listing, download, rename/move/star and delete-to-trash."""

from fastapi import (
    APIRouter,
    Depends,
    File as FastFile,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import client_ip, get_current_user
from app.database import get_db
from app.models import File, User
from app.schemas.common import Message
from app.schemas.file import (
    FileBatch,
    FileCopy,
    FileCreate,
    FileMove,
    FileOut,
    FileRename,
    FileStar,
    FileUpdate,
    UploadResult,
)
from app.schemas.folder import BatchItemError, BatchResult
from app.services import activity_service, file_service, folder_service, share_service, storage_service
from app.services.storage_backend import storage_backend
from app.utils.files import sanitize_display_name

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post(
    "",
    response_model=FileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user-owned Word or Excel document",
)
def create_file(
    payload: FileCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="File name is required")
    record = file_service.create_document_file(db, user, clean_name, payload.type, payload.folder_id)
    db.commit()
    db.refresh(record)
    return record


@router.put(
    "/{file_id}",
    response_model=FileOut,
    summary="Update a user-owned document or spreadsheet, or a shared file with editor permission",
)
def update_file(
    file_id: int,
    payload: FileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.get(File, file_id)
    if record is None or record.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
    
    # Check permissions: owner can always edit, shared files only if editor permission
    if record.user_id != user.id:
        if not share_service.can_user_edit(db, user, record):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have permission to edit this file")
    
    if payload.name is not None:
        record.original_name = sanitize_display_name(payload.name)
        if record.kind == "word" and not record.original_name.lower().endswith(".docx"):
            record.original_name += ".docx"
        if record.kind == "excel" and not record.original_name.lower().endswith(".xlsx"):
            record.original_name += ".xlsx"
    if payload.type is not None:
        record.kind = payload.type
    if payload.document_content is not None and record.kind == "word":
        record.document_content = payload.document_content
    if payload.spreadsheet_data is not None and record.kind == "excel":
        record.spreadsheet_data = payload.spreadsheet_data

    file_service.sync_document_bytes(record)
    storage_service.sync_user_storage(db, record.owner)
    db.commit()
    db.refresh(record)
    return record


@router.post(
    "/upload",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or more files",
)
async def upload_files(
    request: Request,
    files: list[UploadFile] = FastFile(..., description="One or many files"),
    folder_id: int | None = Query(default=None, description="Target folder; omit for My Drive root"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No files were provided")

    # Ownership of the destination is verified once, up front.
    if folder_id is not None:
        folder_service.get_owned_folder(db, user, folder_id)

    uploaded: list[File] = []
    failed: list[dict] = []

    for upload in files:
        try:
            record = file_service.store_upload(
                db=db,
                user=user,
                upload_stream=upload.file,
                original_filename=upload.filename or "untitled",
                content_type=upload.content_type,
                folder_id=folder_id,
                ip_address=client_ip(request),
            )
            uploaded.append(record)
        except HTTPException as exc:
            failed.append({"file_name": upload.filename, "message": exc.detail})
        finally:
            await upload.close()

    db.commit()
    for record in uploaded:
        db.refresh(record)
    db.refresh(user)

    if not uploaded:
        detail = failed[0]["message"] if failed else "Upload failed"
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=detail)

    message = f"{len(uploaded)} file(s) uploaded"
    if failed:
        message += f", {len(failed)} failed"

    return UploadResult(
        message=message,
        uploaded=[FileOut.model_validate(f) for f in uploaded],
        failed=failed,
        storage_used=user.storage_used,
        storage_limit=user.storage_limit,
    )


@router.post(
    "/batch",
    response_model=BatchResult,
    summary="Move, copy, trash or star several files at once",
)
def batch_files(
    payload: FileBatch,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Powers paste and the multi-select toolbar.

    Files are handled one by one so a single failure - a file that ran the
    account out of quota, say - is reported against that file while the rest
    still complete.
    """
    if payload.action in ("move", "copy") and payload.folder_id is not None:
        folder_service.get_owned_folder(db, user, payload.folder_id)

    succeeded: list[int] = []
    failed: list[BatchItemError] = []

    for file_id in payload.file_ids:
        name = None
        # A savepoint per item: one failure rolls back only that item's work,
        # leaving everything that already succeeded intact.
        savepoint = db.begin_nested()
        try:
            record = file_service.get_owned_file(db, user, file_id)
            name = record.original_name

            if payload.action == "move":
                if payload.folder_id != record.folder_id:
                    # A moved file is not a copy, so it gets "(2)" not "(copy)".
                    record.original_name = file_service.unique_file_name(
                        db, user.id, payload.folder_id, record.original_name, marker=None
                    )
                record.folder_id = payload.folder_id
                activity_service.log(
                    db, user.id, activity_service.MOVE_FILE, name, client_ip(request)
                )

            elif payload.action == "copy":
                file_service.copy_file(
                    db, user, record, payload.folder_id, ip_address=client_ip(request)
                )

            elif payload.action == "trash":
                file_service.move_to_trash(db, user, record, client_ip(request))

            else:  # star / unstar
                record.is_starred = payload.action == "star"

            db.flush()
            savepoint.commit()
            succeeded.append(file_id)
        except HTTPException as exc:
            savepoint.rollback()
            failed.append(BatchItemError(id=file_id, name=name, message=str(exc.detail)))

    db.commit()

    verb = {
        "move": "moved",
        "copy": "copied",
        "trash": "moved to Trash",
        "star": "starred",
        "unstar": "unstarred",
    }[payload.action]
    message = f"{len(succeeded)} file(s) {verb}"
    if failed:
        message += f", {len(failed)} failed"

    return BatchResult(
        success=not failed, message=message, succeeded=succeeded, failed=failed
    )


@router.get("", response_model=list[FileOut], summary="List files")
def list_files(
    folder_id: int | None = Query(default=None),
    root_only: bool = Query(default=True, description="When no folder_id, list only root files"),
    starred: bool = Query(default=False),
    recent: bool = Query(default=False),
    limit: int = Query(default=200, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(File).where(File.user_id == user.id, File.is_deleted.is_(False))

    if folder_id is not None:
        folder_service.get_owned_folder(db, user, folder_id)
        stmt = stmt.where(File.folder_id == folder_id)
    elif root_only and not starred and not recent:
        stmt = stmt.where(File.folder_id.is_(None))

    if starred:
        stmt = stmt.where(File.is_starred.is_(True))

    order = File.updated_at.desc() if recent else File.uploaded_at.desc()
    return db.execute(stmt.order_by(order).limit(limit)).scalars().all()


@router.get("/{file_id}", response_model=FileOut, summary="File metadata")
def get_file(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.get(File, file_id)
    if record is None or record.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")
    if not share_service.can_user_access(db, user, record):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have access to this file")
    return record


@router.get("/{file_id}/download", summary="Download a file")
def download_file(
    file_id: int,
    request: Request,
    inline: bool = Query(default=False, description="Render in the browser instead of downloading"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Owners and direct-share recipients only. Files are streamed through this
    endpoint so the uploads directory never has to be publicly reachable."""
    record = db.get(File, file_id)
    if record is None or record.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="File not found")

    if not share_service.can_user_access(db, user, record):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have access to this file")

    if not storage_backend.exists(record.file_path):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="The stored file is missing from storage"
        )

    activity_service.log(
        db, user.id, activity_service.DOWNLOAD, record.original_name, client_ip(request)
    )
    db.commit()

    disposition = "inline" if inline else "attachment"
    return FileResponse(
        path=storage_backend.absolute(record.file_path),
        media_type=record.file_type,
        filename=record.original_name,
        content_disposition_type=disposition,
    )


@router.put("/{file_id}/rename", response_model=FileOut, summary="Rename a file")
def rename_file(
    file_id: int,
    payload: FileRename,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = file_service.get_owned_file(db, user, file_id)
    record.original_name = sanitize_display_name(payload.original_name)
    db.commit()
    db.refresh(record)
    return record


@router.put("/{file_id}/move", response_model=FileOut, summary="Move a file to another folder")
def move_file(
    file_id: int,
    payload: FileMove,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = file_service.get_owned_file(db, user, file_id)
    if payload.folder_id is not None:
        folder_service.get_owned_folder(db, user, payload.folder_id)
    record.folder_id = payload.folder_id
    db.commit()
    db.refresh(record)
    return record


@router.post(
    "/{file_id}/copy",
    response_model=FileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Copy a file into another folder",
)
def copy_file(
    file_id: int,
    payload: FileCopy,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The copy gets its own bytes on disk and counts against the quota, so it
    survives the original being deleted."""
    record = file_service.get_owned_file(db, user, file_id)
    if payload.folder_id is not None:
        folder_service.get_owned_folder(db, user, payload.folder_id)

    duplicate = file_service.copy_file(
        db, user, record, payload.folder_id, ip_address=client_ip(request)
    )
    db.commit()
    db.refresh(duplicate)
    return duplicate


@router.put("/{file_id}/star", response_model=FileOut, summary="Star or unstar a file")
def star_file(
    file_id: int,
    payload: FileStar,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = file_service.get_owned_file(db, user, file_id)
    record.is_starred = payload.is_starred
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{file_id}", response_model=Message, summary="Move a file to Trash")
def delete_file(
    file_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = file_service.get_owned_file(db, user, file_id)
    name = record.original_name
    file_service.move_to_trash(db, user, record, client_ip(request))
    db.commit()
    return Message(message=f"'{name}' moved to Trash")
