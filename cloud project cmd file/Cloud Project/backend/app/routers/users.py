"""Profile management: details, avatar and password."""

from fastapi import APIRouter, Depends, File as FastFile, HTTPException, Request, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import client_ip, get_current_user
from app.auth.security import hash_password, verify_password
from app.database import get_db
from app.models import User
from app.schemas.common import Message
from app.schemas.user import PasswordChange, ProfileUpdate, UserBrief, UserOut
from app.services import activity_service
from app.services.storage_backend import storage_backend
from app.utils.files import extension_of, generate_stored_name

router = APIRouter(prefix="/api/users", tags=["users"])

AVATAR_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
AVATAR_MAX_BYTES = 4 * 1024 * 1024


@router.get("/me", response_model=UserOut, summary="Current user profile")
def get_profile(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserOut, summary="Update profile details")
def update_profile(
    payload: ProfileUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.username:
        taken = db.execute(
            select(User.id).where(
                func.lower(User.username) == payload.username.lower(), User.id != user.id
            )
        ).first()
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This username is already taken")
        user.username = payload.username.lower()

    if payload.email:
        taken = db.execute(
            select(User.id).where(
                func.lower(User.email) == payload.email.lower(), User.id != user.id
            )
        ).first()
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This email is already registered")
        user.email = payload.email.lower()

    if payload.fullname:
        user.fullname = payload.fullname.strip()

    activity_service.log(db, user.id, activity_service.UPDATE_PROFILE, ip_address=client_ip(request))
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/avatar", response_model=UserOut, summary="Upload a profile photo")
def upload_avatar(
    request: Request,
    file: UploadFile = FastFile(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ext = extension_of(file.filename or "")
    if ext not in AVATAR_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Profile photo must be a PNG, JPG, GIF or WEBP image"
        )

    stored_name = generate_stored_name(file.filename or f"avatar{ext}")
    relative = f"users/{user.id}/avatar/{stored_name}"

    try:
        storage_backend.save(relative, file.file, AVATAR_MAX_BYTES)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Profile photo must be under 4 MB")

    old = user.profile_image
    user.profile_image = relative
    activity_service.log(
        db, user.id, activity_service.UPDATE_PROFILE, "profile photo", client_ip(request)
    )
    db.commit()

    if old and old != relative:
        storage_backend.delete(old)

    db.refresh(user)
    return user


@router.get("/me/avatar", summary="Download the current user's profile photo")
def get_avatar(user: User = Depends(get_current_user)):
    from fastapi.responses import FileResponse

    if not user.profile_image or not storage_backend.exists(user.profile_image):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No profile photo set")
    return FileResponse(storage_backend.absolute(user.profile_image))


@router.put("/me/password", response_model=Message, summary="Change password")
def change_password(
    payload: PasswordChange,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    user.password = hash_password(payload.new_password)
    activity_service.log(
        db, user.id, activity_service.UPDATE_PROFILE, "password change", client_ip(request)
    )
    db.commit()
    return Message(message="Password updated")


@router.get("/search", response_model=list[UserBrief], summary="Find users to share with")
def search_users(
    q: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Minimal directory lookup so the share dialog can resolve a recipient.

    Only id, name and username are exposed, never emails or hashes.
    """
    term = q.strip().lower()
    if len(term) < 2:
        return []

    pattern = f"%{term}%"
    rows = db.execute(
        select(User)
        .where(
            User.id != user.id,
            User.status == "active",
            or_(func.lower(User.username).like(pattern), func.lower(User.fullname).like(pattern)),
        )
        .limit(10)
    ).scalars().all()
    return rows
