"""Registration, login, logout and current-user endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import client_ip, get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.models import Setting, User
from app.schemas.common import Message
from app.schemas.user import PasswordReset, TokenResponse, UserLogin, UserOut, UserRegister
from app.services import activity_service, plan_service, storage_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _bootstrap_user(db: Session, user: User) -> None:
    """Every user gets a Storage row, a Settings row and a plan.

    The plan step also renews the picture on the way in: an account whose paid
    plan lapsed while they were away is moved back to Free at login rather than
    silently keeping storage it is no longer entitled to.
    """
    storage_service.sync_user_storage(db, user)
    if db.execute(select(Setting).where(Setting.user_id == user.id)).scalar_one_or_none() is None:
        db.add(Setting(user_id=user.id))
    db.flush()
    plan_service.ensure_subscription(db, user)
    db.flush()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
)
def register(payload: UserRegister, request: Request, db: Session = Depends(get_db)):
    username = payload.username.lower()
    email = payload.email.lower()

    if db.execute(select(User.id).where(func.lower(User.username) == username)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This username is already taken")

    if db.execute(select(User.id).where(func.lower(User.email) == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This email is already registered")

    # Registration never grants administration. The administrator account is
    # created from configuration at startup, so handing admin to whoever signs
    # up first would be a way in, not a convenience.
    user = User(
        fullname=payload.fullname,
        username=username,
        email=email,
        password=hash_password(payload.password),
        role="user",
        storage_limit=float(settings.DEFAULT_STORAGE_LIMIT_MB),
        status="active",
    )
    db.add(user)
    db.flush()

    _bootstrap_user(db, user)
    activity_service.log(db, user.id, activity_service.REGISTER, ip_address=client_ip(request))
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse, summary="Log in with username or email")
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    identifier = payload.username.strip().lower()

    user = db.execute(
        select(User).where(
            or_(func.lower(User.username) == identifier, func.lower(User.email) == identifier)
        )
    ).scalar_one_or_none()

    # Same message for unknown user and wrong password: do not leak which.
    if user is None or not verify_password(payload.password, user.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    if user.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This account has been disabled")

    _bootstrap_user(db, user)
    activity_service.log(db, user.id, activity_service.LOGIN, ip_address=client_ip(request))
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/logout", response_model=Message, summary="Log out the current user")
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    activity_service.log(db, user.id, activity_service.LOGOUT, ip_address=client_ip(request))
    db.commit()
    return Message(message="Logged out")


@router.get("/me", response_model=UserOut, summary="Current authenticated user")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    storage_service.sync_user_storage(db, user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/reset-password", response_model=Message, summary="Reset a password")
def reset_password(payload: PasswordReset, request: Request, db: Session = Depends(get_db)):
    """Development-friendly reset: username and email must both match.

    A production deployment should replace this with an emailed reset token.
    """
    user = db.execute(
        select(User).where(
            func.lower(User.username) == payload.username.lower(),
            func.lower(User.email) == payload.email.lower(),
        )
    ).scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="No account matches that username and email"
        )

    user.password = hash_password(payload.new_password)
    activity_service.log(
        db, user.id, activity_service.UPDATE_PROFILE, "password reset", client_ip(request)
    )
    db.commit()
    return Message(message="Password updated. You can now log in.")
