"""Search across the user's own files and folders plus files shared with them.

All matching is done through SQLAlchemy bound parameters, never string
concatenation, so the query text can never alter the SQL.
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import File, FileShare, Folder, User
from app.routers.shares import _to_out as share_to_out
from app.schemas.dashboard import SearchResults

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResults, summary="Search files, folders and shared files")
def search(
    request: Request,
    q: str = Query(default="", min_length=0, max_length=120),
    limit: int = Query(default=40, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    term = q.strip().lower()
    if not term:
        return SearchResults(query=q)

    pattern = f"%{term}%"

    files = db.execute(
        select(File)
        .where(
            File.user_id == user.id,
            File.is_deleted.is_(False),
            func.lower(File.original_name).like(pattern),
        )
        .order_by(File.updated_at.desc())
        .limit(limit)
    ).scalars().all()

    folders = db.execute(
        select(Folder)
        .where(Folder.user_id == user.id, func.lower(Folder.folder_name).like(pattern))
        .order_by(Folder.folder_name)
        .limit(limit)
    ).scalars().all()

    shares = db.execute(
        select(FileShare)
        .join(File, File.id == FileShare.file_id)
        .join(User, User.id == FileShare.shared_by)
        .where(
            FileShare.shared_to == user.id,
            File.is_deleted.is_(False),
            or_(
                func.lower(File.original_name).like(pattern),
                func.lower(User.fullname).like(pattern),
            ),
        )
        .limit(limit)
    ).scalars().all()

    return SearchResults(
        query=q,
        files=files,
        folders=[
            {
                "id": f.id,
                "folder_name": f.folder_name,
                "parent_folder": f.parent_folder,
                "created_at": f.created_at.isoformat(),
            }
            for f in folders
        ],
        shared=[share_to_out(db, s, str(request.base_url)) for s in shares],
    )
