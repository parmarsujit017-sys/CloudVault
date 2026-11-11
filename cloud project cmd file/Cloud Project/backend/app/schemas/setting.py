from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import ORMModel


class SettingOut(ORMModel):
    id: int
    user_id: int
    theme: str
    notifications: bool
    language: str
    updated_at: datetime


class SettingUpdate(BaseModel):
    theme: Literal["light", "dark"] | None = None
    notifications: bool | None = None
    language: str | None = None
