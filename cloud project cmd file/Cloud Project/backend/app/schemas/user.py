from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

Username = Annotated[str, Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")]
Password = Annotated[str, Field(min_length=6, max_length=72)]


class UserRegister(BaseModel):
    fullname: str = Field(min_length=2, max_length=150)
    username: Username
    email: EmailStr
    password: Password

    @field_validator("fullname")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class UserLogin(BaseModel):
    username: str = Field(min_length=1, max_length=160)  # username or email
    password: str = Field(min_length=1, max_length=72)


class UserOut(ORMModel):
    """Public shape of a user. The password hash is never included."""

    id: int
    fullname: str
    username: str
    email: EmailStr
    role: str
    profile_image: str | None
    storage_used: float
    storage_limit: float
    status: str
    created_at: datetime


class UserBrief(ORMModel):
    id: int
    fullname: str
    username: str
    profile_image: str | None = None


class ProfileUpdate(BaseModel):
    fullname: str | None = Field(default=None, min_length=2, max_length=150)
    username: Username | None = None
    email: EmailStr | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: Password


class PasswordReset(BaseModel):
    email: EmailStr
    username: Username
    new_password: Password


class TokenResponse(BaseModel):
    success: bool = True
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
