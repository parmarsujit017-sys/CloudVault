"""File sharing: direct user shares and password/expiry protected public links."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import client_ip, get_current_user
from app.auth.security import hash_password, verify_password
from app.database import get_db
from app.models import File, FileShare, Folder, FolderShare, User
from app.schemas.common import Message
from app.schemas.share import (
    FolderShareCreate,
    ShareCreate,
    SharedEntry,
    SharedFolderListing,
    ShareOut,
    SharePasswordCheck,
    SharePublicInfo,
)
from app.services import activity_service, file_service, folder_service, share_service
from app.services.storage_backend import storage_backend
from starlette.background import BackgroundTask

router = APIRouter(prefix="/api/shares", tags=["sharing"])


def _to_out(db: Session, share: FileShare, base_url: str | None = None) -> ShareOut:
    record = share.file
    owner = db.get(User, share.shared_by)
    recipient = db.get(User, share.shared_to) if share.shared_to else None

    data = ShareOut.model_validate(share)
    data.kind = "file"
    data.has_password = bool(share.password)
    data.is_expired = share.is_expired
    data.file_name = record.original_name if record else None
    data.file_type = record.file_type if record else None
    data.file_size = record.file_size if record else None
    data.file_kind = record.kind if record else None
    data.shared_by_name = owner.fullname if owner else None
    data.shared_to_name = recipient.fullname if recipient else None
    if base_url:
        data.share_url = share_service.public_url(base_url, share.share_link)
    return data


def _folder_to_out(db: Session, share: FolderShare, base_url: str | None = None) -> ShareOut:
    folder = share.folder
    owner = db.get(User, share.shared_by)
    recipient = db.get(User, share.shared_to) if share.shared_to else None

    data = ShareOut(
        id=share.id,
        kind="folder",
        file_id=None,
        folder_id=share.folder_id,
        shared_by=share.shared_by,
        shared_to=share.shared_to,
        share_link=share.share_link,
        expiry_date=share.expiry_date,
        created_at=share.created_at,
    )
    data.has_password = bool(share.password)
    data.is_expired = share.is_expired
    data.folder_name = folder.folder_name if folder else None
    data.file_name = folder.folder_name if folder else None
    data.file_type = "folder"
    data.shared_by_name = owner.fullname if owner else None
    data.shared_to_name = recipient.fullname if recipient else None

    if folder is not None:
        _, files = folder_service.folder_counts(db, folder.user_id, folder.id)
        data.item_count = files
        data.file_size = sum(
            record.file_size for _, record in folder_service.walk(db, folder.user_id, folder)
        )

    if base_url:
        data.share_url = share_service.public_url(base_url, share.share_link)
    return data


def _resolve_recipient(db: Session, user: User, username: str | None, user_id: int | None):
    """Look a share target up by username/email or id, with the same rules for
    files and folders."""
    recipient: User | None = None

    if username:
        term = username.lower()
        recipient = db.execute(
            select(User).where(
                or_(func.lower(User.username) == term, func.lower(User.email) == term)
            )
        ).scalar_one_or_none()
        if recipient is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No user found with that username")
    elif user_id is not None:
        recipient = db.get(User, user_id)
        if recipient is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Recipient not found")

    if recipient is not None:
        if recipient.id == user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="You already own this item")
        if recipient.status != "active":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="That account is disabled")

    return recipient


@router.post("", response_model=ShareOut, status_code=status.HTTP_201_CREATED, summary="Share a file")
def create_share(
    payload: ShareCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Only the owner of a file may share it."""
    record = file_service.get_owned_file(db, user, payload.file_id)

    recipient = _resolve_recipient(db, user, payload.shared_to_username, payload.shared_to)

    if recipient is not None:
        existing = db.execute(
            select(FileShare).where(
                FileShare.file_id == record.id, FileShare.shared_to == recipient.id
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="This file is already shared with that user"
            )

    if payload.expiry_date is not None and payload.expiry_date <= datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="The expiry date must be in the future")

    share = FileShare(
        file_id=record.id,
        shared_by=user.id,
        shared_to=recipient.id if recipient else None,
        share_link=share_service.generate_token(db),
        password=hash_password(payload.password) if payload.password else None,
        permission=payload.permission,
        expiry_date=payload.expiry_date,
    )
    db.add(share)
    db.flush()

    activity_service.log(
        db, user.id, activity_service.SHARE_FILE, record.original_name, client_ip(request)
    )
    db.commit()
    db.refresh(share)
    return _to_out(db, share, str(request.base_url))


@router.post(
    "/folder",
    response_model=ShareOut,
    status_code=status.HTTP_201_CREATED,
    summary="Share a whole folder",
)
def create_folder_share(
    payload: FolderShareCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Shares the folder and everything under it - subfolders included.

    Access is evaluated live, so files added to the folder afterwards are
    covered too, and files removed from it stop being reachable.
    """
    folder = folder_service.get_owned_folder(db, user, payload.folder_id)
    recipient = _resolve_recipient(db, user, payload.shared_to_username, payload.shared_to)

    if recipient is not None:
        existing = db.execute(
            select(FolderShare).where(
                FolderShare.folder_id == folder.id, FolderShare.shared_to == recipient.id
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="This folder is already shared with that user"
            )

    if payload.expiry_date is not None and payload.expiry_date <= datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="The expiry date must be in the future")

    share = FolderShare(
        folder_id=folder.id,
        shared_by=user.id,
        shared_to=recipient.id if recipient else None,
        share_link=share_service.generate_token(db),
        password=hash_password(payload.password) if payload.password else None,
        permission=payload.permission,
        expiry_date=payload.expiry_date,
    )
    db.add(share)
    db.flush()

    activity_service.log(
        db, user.id, activity_service.SHARE_FOLDER, folder.folder_name, client_ip(request)
    )
    db.commit()
    db.refresh(share)
    return _folder_to_out(db, share, str(request.base_url))


@router.delete("/folder/{share_id}", response_model=Message, summary="Revoke a folder share")
def revoke_folder_share(
    share_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    share = db.get(FolderShare, share_id)
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Share not found")
    if share.shared_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You did not create this share")

    name = share.folder.folder_name if share.folder else None
    db.delete(share)
    activity_service.log(db, user.id, activity_service.UNSHARE_FOLDER, name, client_ip(request))
    db.commit()
    return Message(message="Share revoked")


@router.get("/sent", response_model=list[ShareOut], summary="Shares the current user created")
def sent_shares(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    base = str(request.base_url)

    files = db.execute(
        select(FileShare).where(FileShare.shared_by == user.id).order_by(FileShare.created_at.desc())
    ).scalars().all()
    folders = db.execute(
        select(FolderShare)
        .where(FolderShare.shared_by == user.id)
        .order_by(FolderShare.created_at.desc())
    ).scalars().all()

    out = [_to_out(db, s, base) for s in files if s.file is not None]
    out += [_folder_to_out(db, s, base) for s in folders if s.folder is not None]
    out.sort(key=lambda share: share.created_at, reverse=True)
    return out


@router.get("/received", response_model=list[ShareOut], summary="Files shared with the current user")
def received_shares(
    request: Request,
    q: str = Query(default="", description="Optional search over file name or owner"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(FileShare)
        .join(File, File.id == FileShare.file_id)
        .where(FileShare.shared_to == user.id, File.is_deleted.is_(False))
        .order_by(FileShare.created_at.desc())
    )

    term = q.strip().lower()
    if term:
        pattern = f"%{term}%"
        stmt = stmt.join(User, User.id == FileShare.shared_by).where(
            or_(
                func.lower(File.original_name).like(pattern),
                func.lower(User.fullname).like(pattern),
                func.lower(User.username).like(pattern),
            )
        )

    base = str(request.base_url)
    out = [_to_out(db, s, base) for s in db.execute(stmt).scalars().all()]

    folder_stmt = (
        select(FolderShare)
        .join(Folder, Folder.id == FolderShare.folder_id)
        .where(FolderShare.shared_to == user.id)
        .order_by(FolderShare.created_at.desc())
    )
    if term:
        folder_pattern = f"%{term}%"
        folder_stmt = folder_stmt.join(User, User.id == FolderShare.shared_by).where(
            or_(
                func.lower(Folder.folder_name).like(folder_pattern),
                func.lower(User.fullname).like(folder_pattern),
                func.lower(User.username).like(folder_pattern),
            )
        )

    out += [
        _folder_to_out(db, s, base)
        for s in db.execute(folder_stmt).scalars().all()
        if s.folder is not None
    ]
    out.sort(key=lambda share: share.created_at, reverse=True)
    return out


@router.delete("/{share_id}", response_model=Message, summary="Revoke a share")
def revoke_share(
    share_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    share = db.get(FileShare, share_id)
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Share not found")
    if share.shared_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You did not create this share")

    name = share.file.original_name if share.file else None
    db.delete(share)
    activity_service.log(db, user.id, activity_service.UNSHARE_FILE, name, client_ip(request))
    db.commit()
    return Message(message="Share revoked")


# ---------------------------------------------------------------------------
# Public link endpoints - no authentication, token plus optional password only.
# ---------------------------------------------------------------------------

public_router = APIRouter(prefix="/api/share", tags=["public share"])


@public_router.get("/{token}", response_model=SharePublicInfo, summary="Inspect a public share link")
def share_info(token: str, db: Session = Depends(get_db)):
    """One entry point for both kinds of link: the token itself decides whether
    the visitor is looking at a single file or a whole folder."""
    kind, share = share_service.resolve_token(db, token)
    owner = db.get(User, share.shared_by)
    shared_by_name = owner.fullname if owner else "Unknown"

    if kind == "file":
        record = share_service.assert_usable(share)
        return SharePublicInfo(
            kind="file",
            file_name=record.original_name,
            file_type=record.file_type,
            file_size=record.file_size,
            shared_by_name=shared_by_name,
            created_at=share.created_at,
            expiry_date=share.expiry_date,
            requires_password=bool(share.password),
        )

    folder = share_service.assert_folder_usable(share)
    contents = folder_service.walk(db, folder.user_id, folder)
    subfolders, _ = folder_service.folder_counts(db, folder.user_id, folder.id)

    return SharePublicInfo(
        kind="folder",
        file_name=folder.folder_name,
        file_type="folder",
        file_size=sum(record.file_size for _, record in contents),
        shared_by_name=shared_by_name,
        created_at=share.created_at,
        expiry_date=share.expiry_date,
        requires_password=bool(share.password),
        item_count=len(contents),
        folder_count=subfolders,
    )


@public_router.post("/{token}/verify", response_model=Message, summary="Check a share password")
def verify_share_password(token: str, payload: SharePasswordCheck, db: Session = Depends(get_db)):
    kind, share = share_service.resolve_token(db, token)
    if kind == "file":
        share_service.assert_usable(share)
    else:
        share_service.assert_folder_usable(share)

    if not share.password:
        return Message(message="This link is not password protected")
    if not verify_password(payload.password, share.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    return Message(message="Password accepted")


def _check_link_password(share, password: str | None) -> None:
    if share.password and (not password or not verify_password(password, share.password)):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="A valid password is required for this link"
        )


def _descend(db: Session, root: Folder, path: str) -> Folder:
    """Walk a `sub/dir` path down from the share root.

    Visitors navigate by name rather than by id, so a link can never be used to
    reach a folder outside the share.
    """
    current = root
    for segment in folder_service.split_segments(path):
        child = folder_service.find_child(db, root.user_id, current.id, segment)
        if child is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="That folder is not in this share")
        current = child
    return current


@public_router.get(
    "/{token}/list",
    response_model=SharedFolderListing,
    summary="Browse inside a shared folder",
)
def share_list(
    token: str,
    path: str = Query(default="", description="Path relative to the shared folder"),
    password: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Lists one level at a time, so a deep share opens instantly and the visitor
    walks it exactly like the owner does."""
    share = share_service.get_folder_share_by_token(db, token)
    root = share_service.assert_folder_usable(share)
    _check_link_password(share, password)

    current = _descend(db, root, path)
    prefix = "/".join(folder_service.split_segments(path))

    entries: list[SharedEntry] = []

    children = db.execute(
        select(Folder)
        .where(Folder.user_id == root.user_id, Folder.parent_folder == current.id)
        .order_by(Folder.folder_name)
    ).scalars().all()
    for child in children:
        _, file_count = folder_service.folder_counts(db, root.user_id, child.id)
        entries.append(SharedEntry(
            kind="folder",
            name=child.folder_name,
            path=f"{prefix}/{child.folder_name}" if prefix else child.folder_name,
            item_count=file_count,
        ))

    records = db.execute(
        select(File)
        .where(
            File.user_id == root.user_id,
            File.folder_id == current.id,
            File.is_deleted.is_(False),
        )
        .order_by(File.original_name)
    ).scalars().all()
    for record in records:
        entries.append(SharedEntry(
            kind="file",
            name=record.original_name,
            path=f"{prefix}/{record.original_name}" if prefix else record.original_name,
            file_id=record.id,
            file_type=record.file_type,
            file_size=record.file_size,
            file_kind=record.kind,
            updated_at=record.updated_at,
        ))

    return SharedFolderListing(
        folder_name=current.folder_name,
        path=prefix,
        breadcrumb=folder_service.split_segments(path),
        entries=entries,
    )


@public_router.get("/{token}/download", summary="Download via a public share link")
def share_download(
    token: str,
    request: Request,
    file_id: int | None = Query(
        default=None, description="Which file to fetch, for a folder link"
    ),
    password: str | None = Query(default=None, description="Required when the link is protected"),
    db: Session = Depends(get_db),
):
    kind, share = share_service.resolve_token(db, token)

    if kind == "file":
        record = share_service.assert_usable(share)
        _check_link_password(share, password)
    else:
        folder = share_service.assert_folder_usable(share)
        _check_link_password(share, password)

        if file_id is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="Choose a file inside this folder to download"
            )

        record = db.get(File, file_id)
        allowed = folder_service.descendant_ids(db, folder.user_id, folder.id)
        if (
            record is None
            or record.is_deleted
            or record.user_id != folder.user_id
            or record.folder_id not in allowed
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="That file is not in this share")

    if not storage_backend.exists(record.file_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="The stored file is missing")

    # Logged against the owner, since a public visitor has no account.
    activity_service.log(
        db, share.shared_by, activity_service.DOWNLOAD, record.original_name, client_ip(request)
    )
    db.commit()

    return FileResponse(
        path=storage_backend.absolute(record.file_path),
        media_type=record.file_type,
        filename=record.original_name,
    )


@public_router.get("/{token}/download-all", summary="Download a shared folder as a .zip")
def share_download_all(
    token: str,
    request: Request,
    path: str = Query(default="", description="Download a subfolder instead of the whole share"),
    password: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    share = share_service.get_folder_share_by_token(db, token)
    root = share_service.assert_folder_usable(share)
    _check_link_password(share, password)

    target = _descend(db, root, path)
    archive = folder_service.build_zip(db, root.user_id, target)

    activity_service.log(
        db, share.shared_by, activity_service.DOWNLOAD, target.folder_name, client_ip(request)
    )
    db.commit()

    return FileResponse(
        path=archive,
        media_type="application/zip",
        filename=f"{target.folder_name}.zip",
        background=BackgroundTask(archive.unlink, missing_ok=True),
    )
