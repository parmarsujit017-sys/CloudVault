"""Activity logging."""

from sqlalchemy.orm import Session

from app.models import ActivityLog

# Every action recorded by the app.
LOGIN = "LOGIN"
LOGOUT = "LOGOUT"
REGISTER = "REGISTER"
UPLOAD = "UPLOAD"
DOWNLOAD = "DOWNLOAD"
CREATE_FOLDER = "CREATE_FOLDER"
RENAME_FOLDER = "RENAME_FOLDER"
DELETE_FOLDER = "DELETE_FOLDER"
DELETE_FILE = "DELETE_FILE"
RESTORE_FILE = "RESTORE_FILE"
PERMANENT_DELETE = "PERMANENT_DELETE"
SHARE_FILE = "SHARE_FILE"
UNSHARE_FILE = "UNSHARE_FILE"
SHARE_FOLDER = "SHARE_FOLDER"
UNSHARE_FOLDER = "UNSHARE_FOLDER"
COPY_FILE = "COPY_FILE"
COPY_FOLDER = "COPY_FOLDER"
MOVE_FILE = "MOVE_FILE"
MOVE_FOLDER = "MOVE_FOLDER"
UPDATE_PROFILE = "UPDATE_PROFILE"
UPDATE_SETTINGS = "UPDATE_SETTINGS"

# Plans and administration.
PLAN_CHANGED = "PLAN_CHANGED"
ADMIN_ASSIGN_PLAN = "ADMIN_ASSIGN_PLAN"
ADMIN_CREATE_PLAN = "ADMIN_CREATE_PLAN"
ADMIN_UPDATE_PLAN = "ADMIN_UPDATE_PLAN"
ADMIN_DELETE_PLAN = "ADMIN_DELETE_PLAN"
ADMIN_UPDATE_USER = "ADMIN_UPDATE_USER"
ADMIN_DELETE_USER = "ADMIN_DELETE_USER"


def log(
    db: Session,
    user_id: int,
    activity: str,
    file_name: str | None = None,
    ip_address: str | None = None,
    commit: bool = False,
) -> ActivityLog:
    entry = ActivityLog(
        user_id=user_id,
        activity=activity,
        file_name=file_name,
        ip_address=ip_address,
    )
    db.add(entry)
    if commit:
        db.commit()
    else:
        db.flush()
    return entry
