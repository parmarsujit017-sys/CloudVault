"""Folder ownership and tree helpers."""

from __future__ import annotations

import os
import tempfile
import zipfile
from itertools import islice
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import File, Folder, User
from app.services import activity_service
from app.services.storage_backend import storage_backend
from app.utils.files import sanitize_display_name

MAX_DEPTH = 20

# Ceiling on how much a single copy / upload-tree request may touch, so one
# request can never walk away with the whole database.
MAX_TREE_NODES = 2000


def get_owned_folder(db: Session, user: User, folder_id: int) -> Folder:
    """Fetch a folder, 404 if missing, 403 if it belongs to somebody else.

    Never trust a folder id coming from the client without this.
    """
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Folder not found")
    if folder.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have access to this folder")
    return folder


def breadcrumb(db: Session, folder: Folder | None) -> list[dict]:
    trail: list[dict] = []
    current = folder
    guard = 0
    while current is not None and guard < MAX_DEPTH:
        trail.append({"id": current.id, "folder_name": current.folder_name})
        current = db.get(Folder, current.parent_folder) if current.parent_folder else None
        guard += 1
    trail.reverse()
    return trail


def depth_of(db: Session, folder: Folder | None) -> int:
    return len(breadcrumb(db, folder))


def descendant_ids(db: Session, user_id: int, folder_id: int) -> list[int]:
    """All folder ids in the subtree rooted at folder_id, including itself."""
    collected = [folder_id]
    frontier = [folder_id]
    guard = 0
    while frontier and guard < 1000:
        guard += 1
        rows = db.execute(
            select(Folder.id).where(
                Folder.user_id == user_id, Folder.parent_folder.in_(frontier)
            )
        ).scalars().all()
        rows = [r for r in rows if r not in collected]
        collected.extend(rows)
        frontier = rows
    return collected


def would_create_cycle(db: Session, folder_id: int, new_parent_id: int | None) -> bool:
    if new_parent_id is None:
        return False
    if new_parent_id == folder_id:
        return True
    current = db.get(Folder, new_parent_id)
    guard = 0
    while current is not None and guard < MAX_DEPTH + 5:
        if current.id == folder_id:
            return True
        current = db.get(Folder, current.parent_folder) if current.parent_folder else None
        guard += 1
    return False


def folder_counts(db: Session, user_id: int, folder_id: int) -> tuple[int, int]:
    """(subfolder count, live file count) for the whole subtree."""
    ids = descendant_ids(db, user_id, folder_id)
    files = db.execute(
        select(File.id).where(
            File.user_id == user_id, File.folder_id.in_(ids), File.is_deleted.is_(False)
        )
    ).scalars().all()
    return len(ids) - 1, len(files)


# ---------------------------------------------------------------------------
# Path resolution - used when a whole folder is uploaded at once
# ---------------------------------------------------------------------------


def split_segments(raw_path: str) -> list[str]:
    """Turn a browser-supplied relative path into safe folder names.

    `webkitRelativePath` arrives as `Photos/2024/Trip/beach.jpg`. Separators are
    normalised, `.`/`..` segments are dropped and every remaining segment goes
    through the same sanitiser as a typed folder name, so a crafted path can
    never escape the user's own tree.
    """
    parts = (raw_path or "").replace("\\", "/").split("/")
    clean: list[str] = []
    for part in parts:
        part = part.strip()
        if not part or part in (".", ".."):
            continue
        clean.append(sanitize_display_name(part))
    return clean


def find_child(db: Session, user_id: int, parent_id: int | None, name: str) -> Folder | None:
    """Case-insensitive lookup of a direct subfolder, matching create_folder."""
    return db.execute(
        select(Folder).where(
            Folder.user_id == user_id,
            Folder.parent_folder.is_(None) if parent_id is None else Folder.parent_folder == parent_id,
            func.lower(Folder.folder_name) == name.lower(),
        )
    ).scalars().first()


def ensure_tree(
    db: Session, user: User, parent_id: int | None, paths: list[str]
) -> tuple[dict[str, int], int]:
    """Materialise every directory in `paths` under `parent_id`.

    Existing folders are reused rather than duplicated, so re-uploading a folder
    merges into the one already there instead of creating `Photos (2)`. Returns
    the map of relative path -> folder id plus how many folders were created.
    """
    base_depth = 0
    if parent_id is not None:
        base_depth = depth_of(db, get_owned_folder(db, user, parent_id))

    wanted: set[str] = set()
    for raw in paths:
        segments = split_segments(raw)
        for index in range(1, len(segments) + 1):
            wanted.add("/".join(segments[:index]))

    if len(wanted) > MAX_TREE_NODES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"That upload contains more than {MAX_TREE_NODES} folders",
        )

    resolved: dict[str, int | None] = {"": parent_id}
    created = 0

    # Shallowest first, so a parent always exists before its children.
    for key in sorted(wanted, key=lambda path: (path.count("/"), path.lower())):
        segments = key.split("/")
        parent_key = "/".join(segments[:-1])
        holder = resolved.get(parent_key)

        if base_depth + len(segments) > MAX_DEPTH:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="Folders are nested too deeply"
            )

        existing = find_child(db, user.id, holder, segments[-1])
        if existing is None:
            existing = Folder(user_id=user.id, folder_name=segments[-1], parent_folder=holder)
            db.add(existing)
            db.flush()
            created += 1

        resolved[key] = existing.id

    resolved.pop("", None)
    return {key: value for key, value in resolved.items() if value is not None}, created


def name_variants(name: str, marker: str | None) -> Iterator[str]:
    """Successive fallbacks for a name that is already taken.

    With a marker: `Reports (copy)`, `Reports (copy 2)`, ... - right when the
    item really is a duplicate. Without one: `Reports (2)`, `Reports (3)`, ... -
    which is what a *move* wants, since calling a moved folder a copy would be
    a plain lie about what just happened.
    """
    if marker:
        yield f"{name} ({marker})"

    index = 2
    while True:
        yield f"{name} ({marker} {index})" if marker else f"{name} ({index})"
        index += 1


def unique_name(
    db: Session, user_id: int, parent_id: int | None, name: str, marker: str | None = "copy"
) -> str:
    """A name no sibling folder is using yet."""
    if find_child(db, user_id, parent_id, name) is None:
        return name

    for candidate in islice(name_variants(name, marker), 500):
        if find_child(db, user_id, parent_id, candidate) is None:
            return candidate

    raise HTTPException(
        status.HTTP_409_CONFLICT, detail="Too many folders here share that name"
    )


def subtree_height(db: Session, user_id: int, folder_id: int) -> int:
    """Levels below `folder_id`, counting the folder itself as 1."""
    level = 1
    frontier = [folder_id]
    while frontier and level < MAX_DEPTH + 2:
        rows = db.execute(
            select(Folder.id).where(Folder.user_id == user_id, Folder.parent_folder.in_(frontier))
        ).scalars().all()
        if not rows:
            break
        level += 1
        frontier = rows
    return level


def walk(db: Session, user_id: int, folder: Folder) -> list[tuple[str, File]]:
    """Every live file in the subtree paired with its path relative to `folder`.

    The paths are what makes a folder download or a shared-folder listing show
    the same structure the user built, rather than one flat pile of files.
    """
    entries: list[tuple[str, File]] = []
    frontier: list[tuple[Folder, str]] = [(folder, "")]
    guard = 0

    while frontier and guard < MAX_TREE_NODES:
        current, prefix = frontier.pop()
        guard += 1

        files = db.execute(
            select(File)
            .where(File.user_id == user_id, File.folder_id == current.id, File.is_deleted.is_(False))
            .order_by(File.original_name)
        ).scalars().all()
        for record in files:
            entries.append((prefix + record.original_name, record))

        children = db.execute(
            select(Folder)
            .where(Folder.user_id == user_id, Folder.parent_folder == current.id)
            .order_by(Folder.folder_name)
        ).scalars().all()
        for child in children:
            frontier.append((child, f"{prefix}{child.folder_name}/"))

    return entries


def subtree_folders(db: Session, user_id: int, folder: Folder) -> list[tuple[str, Folder]]:
    """Every descendant folder paired with its path relative to `folder`."""
    found: list[tuple[str, Folder]] = []
    frontier: list[tuple[Folder, str]] = [(folder, "")]
    guard = 0

    while frontier and guard < MAX_TREE_NODES:
        current, prefix = frontier.pop()
        guard += 1

        children = db.execute(
            select(Folder)
            .where(Folder.user_id == user_id, Folder.parent_folder == current.id)
            .order_by(Folder.folder_name)
        ).scalars().all()
        for child in children:
            path = f"{prefix}{child.folder_name}"
            found.append((path, child))
            frontier.append((child, path + "/"))

    return found


# ---------------------------------------------------------------------------
# Copying
# ---------------------------------------------------------------------------


def copy_folder(
    db: Session,
    user: User,
    source: Folder,
    target_parent: int | None,
    ip_address: str | None = None,
) -> tuple[Folder, int]:
    """Deep copy `source` (and everything under it) into `target_parent`.

    Returns the new root folder and the number of files copied. Copying a folder
    into itself or into one of its own descendants is refused - that would
    recurse forever.
    """
    from app.services import file_service  # local import keeps the modules acyclic

    if target_parent is not None:
        get_owned_folder(db, user, target_parent)
        if target_parent in descendant_ids(db, user.id, source.id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="A folder cannot be copied inside itself"
            )

    base_depth = 0
    if target_parent is not None:
        base_depth = depth_of(db, db.get(Folder, target_parent))
    if base_depth + subtree_height(db, user.id, source.id) > MAX_DEPTH:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Folders are nested too deeply")

    root = Folder(
        user_id=user.id,
        folder_name=unique_name(db, user.id, target_parent, source.folder_name),
        parent_folder=target_parent,
    )
    db.add(root)
    db.flush()

    copied_files = 0
    visited = 0
    frontier: list[tuple[Folder, Folder]] = [(source, root)]

    while frontier:
        original, clone = frontier.pop()
        visited += 1
        if visited > MAX_TREE_NODES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"That folder holds more than {MAX_TREE_NODES} items to copy",
            )

        files = db.execute(
            select(File).where(
                File.user_id == user.id,
                File.folder_id == original.id,
                File.is_deleted.is_(False),
            )
        ).scalars().all()
        for record in files:
            # Names are unique inside a freshly created folder, so no clash check.
            file_service.copy_file(db, user, record, clone.id, rename_on_clash=False)
            copied_files += 1

        children = db.execute(
            select(Folder).where(Folder.user_id == user.id, Folder.parent_folder == original.id)
        ).scalars().all()
        for child in children:
            child_clone = Folder(
                user_id=user.id, folder_name=child.folder_name, parent_folder=clone.id
            )
            db.add(child_clone)
            db.flush()
            frontier.append((child, child_clone))

    if ip_address is not None:
        activity_service.log(
            db, user.id, activity_service.COPY_FOLDER, root.folder_name, ip_address
        )
    return root, copied_files


def build_zip(db: Session, user_id: int, folder: Folder) -> Path:
    """Write the folder's subtree to a temporary .zip and return its path.

    Empty subfolders are written as directory entries so the archive really does
    mirror what the user sees, not just the files that happen to be in it.
    """
    handle, temp_name = tempfile.mkstemp(prefix="Cloud-zip-", suffix=".zip")
    os.close(handle)
    archive_path = Path(temp_name)

    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            files = walk(db, user_id, folder)
            for relative, record in files:
                if not storage_backend.exists(record.file_path):
                    continue  # a missing blob must not sink the whole download
                archive.write(storage_backend.absolute(record.file_path), arcname=relative)

            occupied = {path.rsplit("/", 1)[0] for path, _ in files if "/" in path}
            for path, _ in subtree_folders(db, user_id, folder):
                if path not in occupied and not any(p.startswith(path + "/") for p in occupied):
                    archive.writestr(path + "/", b"")
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise

    return archive_path
