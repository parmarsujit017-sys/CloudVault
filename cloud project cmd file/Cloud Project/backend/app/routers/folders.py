"""Folder CRUD with nesting, breadcrumbs and ownership enforcement."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.auth.deps import client_ip, get_current_user
from app.database import get_db
from app.models import File, Folder, User
from app.schemas.common import Message
from app.schemas.folder import (
    BatchItemError,
    BatchResult,
    FolderBatch,
    FolderContents,
    FolderCopy,
    FolderCreate,
    FolderOut,
    FolderTreeCreate,
    FolderTreeResult,
    FolderUpdate,
)
from app.services import activity_service, file_service, folder_service
from app.utils.files import sanitize_display_name

router = APIRouter(prefix="/api/folders", tags=["folders"])


def _to_out(db: Session, folder: Folder) -> FolderOut:
    sub, files = folder_service.folder_counts(db, folder.user_id, folder.id)
    data = FolderOut.model_validate(folder)
    data.subfolder_count = sub
    data.file_count = files
    return data


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED, summary="Create a folder")
def create_folder(
    payload: FolderCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = sanitize_display_name(payload.folder_name)

    parent = None
    if payload.parent_folder is not None:
        parent = folder_service.get_owned_folder(db, user, payload.parent_folder)
        if folder_service.depth_of(db, parent) >= folder_service.MAX_DEPTH:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Folders are nested too deeply")

    duplicate = db.execute(
        select(Folder.id).where(
            Folder.user_id == user.id,
            Folder.parent_folder.is_(None) if parent is None else Folder.parent_folder == parent.id,
            func.lower(Folder.folder_name) == name.lower(),
        )
    ).first()
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A folder with that name already exists here")

    folder = Folder(user_id=user.id, folder_name=name, parent_folder=parent.id if parent else None)
    db.add(folder)
    db.flush()

    activity_service.log(db, user.id, activity_service.CREATE_FOLDER, name, client_ip(request))
    db.commit()
    db.refresh(folder)
    return _to_out(db, folder)


@router.post(
    "/tree",
    response_model=FolderTreeResult,
    status_code=status.HTTP_201_CREATED,
    summary="Create a whole directory tree in one call",
)
def create_tree(
    payload: FolderTreeCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Backs "Upload folder" and dropping a folder onto the page.

    The browser sends every directory path it found inside the dropped folder
    and gets back a path -> id map, so each file can then be uploaded straight
    into the folder it came from. Paths that already exist are reused, which
    makes re-uploading a folder merge rather than duplicate.
    """
    if not payload.paths:
        return FolderTreeResult(message="No folders to create", created=0)

    mapping, created = folder_service.ensure_tree(db, user, payload.parent_folder, payload.paths)

    resolved = {}
    for raw in payload.paths:
        key = "/".join(folder_service.split_segments(raw))
        if key in mapping:
            resolved[raw] = mapping[key]

    if created:
        # One entry for the upload as a whole; a line per subfolder would bury
        # everything else in the activity log.
        root = min(mapping, key=lambda path: (path.count("/"), path.lower()))
        activity_service.log(db, user.id, activity_service.CREATE_FOLDER, root, client_ip(request))

    db.commit()
    return FolderTreeResult(
        message=f"{created} folder(s) created",
        created=created,
        folders=mapping,
        resolved=resolved,
    )


@router.post(
    "/batch",
    response_model=BatchResult,
    summary="Move, copy or delete several folders at once",
)
def batch_folders(
    payload: FolderBatch,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Powers paste and the multi-select toolbar.

    Each folder is handled independently: one failure (a name clash, a folder
    dropped into itself) is reported against that folder and the rest still go
    through.
    """
    if payload.action in ("move", "copy") and payload.parent_folder is not None:
        folder_service.get_owned_folder(db, user, payload.parent_folder)

    succeeded: list[int] = []
    failed: list[BatchItemError] = []

    for folder_id in payload.folder_ids:
        name = None
        # A savepoint per item: one failure rolls back only that item's work,
        # leaving everything that already succeeded intact.
        savepoint = db.begin_nested()
        try:
            folder = folder_service.get_owned_folder(db, user, folder_id)
            name = folder.folder_name

            if payload.action == "move":
                if folder_service.would_create_cycle(db, folder.id, payload.parent_folder):
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail="A folder cannot be moved inside itself",
                    )
                if payload.parent_folder != folder.parent_folder:
                    # A moved folder is not a copy, so it gets "(2)" not "(copy)".
                    folder.folder_name = folder_service.unique_name(
                        db, user.id, payload.parent_folder, folder.folder_name, marker=None
                    )
                folder.parent_folder = payload.parent_folder
                activity_service.log(
                    db, user.id, activity_service.MOVE_FOLDER, name, client_ip(request)
                )

            elif payload.action == "copy":
                folder_service.copy_folder(
                    db, user, folder, payload.parent_folder, client_ip(request)
                )

            else:  # delete
                _trash_folder(db, user, folder, client_ip(request))

            db.flush()
            savepoint.commit()
            succeeded.append(folder_id)
        except HTTPException as exc:
            savepoint.rollback()
            failed.append(BatchItemError(id=folder_id, name=name, message=str(exc.detail)))

    db.commit()

    verb = {"move": "moved", "copy": "copied", "delete": "deleted"}[payload.action]
    message = f"{len(succeeded)} folder(s) {verb}"
    if failed:
        message += f", {len(failed)} failed"

    return BatchResult(
        success=not failed, message=message, succeeded=succeeded, failed=failed
    )


@router.get("", response_model=list[FolderOut], summary="List folders (optionally by parent)")
def list_folders(
    parent: int | None = Query(default=None, description="Parent folder id; omit for the root"),
    all_folders: bool = Query(default=False, alias="all", description="Return the whole tree"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Folder).where(Folder.user_id == user.id)
    if not all_folders:
        stmt = stmt.where(
            Folder.parent_folder.is_(None) if parent is None else Folder.parent_folder == parent
        )
        if parent is not None:
            folder_service.get_owned_folder(db, user, parent)

    rows = db.execute(stmt.order_by(Folder.folder_name)).scalars().all()
    return [_to_out(db, f) for f in rows]


@router.get("/{folder_id}", response_model=FolderContents, summary="Open a folder")
def open_folder(
    folder_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    folder = folder_service.get_owned_folder(db, user, folder_id)

    subfolders = db.execute(
        select(Folder)
        .where(Folder.user_id == user.id, Folder.parent_folder == folder.id)
        .order_by(Folder.folder_name)
    ).scalars().all()

    files = db.execute(
        select(File)
        .where(File.user_id == user.id, File.folder_id == folder.id, File.is_deleted.is_(False))
        .order_by(File.uploaded_at.desc())
    ).scalars().all()

    return FolderContents(
        folder=_to_out(db, folder),
        breadcrumb=folder_service.breadcrumb(db, folder),
        folders=[_to_out(db, f) for f in subfolders],
        files=files,
    )


@router.put("/{folder_id}", response_model=FolderOut, summary="Rename or move a folder")
def update_folder(
    folder_id: int,
    payload: FolderUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    folder = folder_service.get_owned_folder(db, user, folder_id)

    if payload.folder_name:
        folder.folder_name = sanitize_display_name(payload.folder_name)

    if "parent_folder" in payload.model_fields_set:
        new_parent = payload.parent_folder
        if new_parent is not None:
            folder_service.get_owned_folder(db, user, new_parent)
        if folder_service.would_create_cycle(db, folder.id, new_parent):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="A folder cannot be moved inside itself"
            )
        folder.parent_folder = new_parent

    activity_service.log(
        db, user.id, activity_service.RENAME_FOLDER, folder.folder_name, client_ip(request)
    )
    db.commit()
    db.refresh(folder)
    return _to_out(db, folder)


@router.delete("/{folder_id}", response_model=Message, summary="Delete a folder and trash its files")
def delete_folder(
    folder_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The folder tree is removed; the files inside it go to Trash rather than
    being destroyed, so nothing is lost by accident."""
    folder = folder_service.get_owned_folder(db, user, folder_id)
    name = folder.folder_name
    count = _trash_folder(db, user, folder, client_ip(request))
    db.commit()
    return Message(message=f"Folder '{name}' deleted, {count} file(s) moved to Trash")


def _trash_folder(db: Session, user: User, folder: Folder, ip: str | None) -> int:
    """Delete a folder tree, sending its files to Trash. Returns the file count."""
    name = folder.folder_name

    ids = folder_service.descendant_ids(db, user.id, folder.id)
    files = db.execute(
        select(File).where(
            File.user_id == user.id, File.folder_id.in_(ids), File.is_deleted.is_(False)
        )
    ).scalars().all()

    for record in files:
        record.folder_id = None
        file_service.move_to_trash(db, user, record, ip)

    db.delete(folder)
    db.flush()

    activity_service.log(db, user.id, activity_service.DELETE_FOLDER, name, ip)
    return len(files)


@router.post(
    "/{folder_id}/copy",
    response_model=FolderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Copy a folder and everything inside it",
)
def copy_folder(
    folder_id: int,
    payload: FolderCopy,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """A real deep copy: every subfolder is recreated and every file's bytes are
    duplicated, so the copy is independent of the original from then on."""
    folder = folder_service.get_owned_folder(db, user, folder_id)
    root, _ = folder_service.copy_folder(
        db, user, folder, payload.parent_folder, client_ip(request)
    )
    db.commit()
    db.refresh(root)
    return _to_out(db, root)


@router.get("/{folder_id}/download", summary="Download a folder as a .zip archive")
def download_folder(
    folder_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The archive keeps the folder structure, so unzipping it gives back exactly
    the tree the user built here."""
    folder = folder_service.get_owned_folder(db, user, folder_id)
    archive = folder_service.build_zip(db, user.id, folder)

    activity_service.log(
        db, user.id, activity_service.DOWNLOAD, folder.folder_name, client_ip(request)
    )
    db.commit()

    return FileResponse(
        path=archive,
        media_type="application/zip",
        filename=f"{folder.folder_name}.zip",
        # The archive is a scratch file: delete it once the response is sent.
        background=BackgroundTask(archive.unlink, missing_ok=True),
    )
