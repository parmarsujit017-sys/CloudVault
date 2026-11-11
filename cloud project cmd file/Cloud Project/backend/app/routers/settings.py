"""Per-user settings: theme, notifications and language."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import client_ip, get_current_user
from app.database import get_db
from app.models import Setting, User
from app.schemas.setting import SettingOut, SettingUpdate
from app.services import activity_service

router = APIRouter(prefix="/api/settings", tags=["settings"])

LANGUAGES = {"English", "Hindi", "Gujarati"}


def _get_or_create(db: Session, user: User) -> Setting:
    row = db.execute(select(Setting).where(Setting.user_id == user.id)).scalar_one_or_none()
    if row is None:
        row = Setting(user_id=user.id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=SettingOut, summary="Read the current user's settings")
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_or_create(db, user)


@router.put("", response_model=SettingOut, summary="Update settings")
def update_settings(
    payload: SettingUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_or_create(db, user)

    if payload.theme is not None:
        row.theme = payload.theme
    if payload.notifications is not None:
        row.notifications = payload.notifications
    if payload.language is not None and payload.language in LANGUAGES:
        row.language = payload.language

    activity_service.log(db, user.id, activity_service.UPDATE_SETTINGS, ip_address=client_ip(request))
    db.commit()
    db.refresh(row)
    return row
