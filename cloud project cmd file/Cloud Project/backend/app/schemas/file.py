from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.user import UserBrief


class FileOut(ORMModel):
    id: int
    user_id: int
    folder_id: int | None
    file_name: str
    original_name: str
    kind: str = "file"
    type: str = "file"
    file_type: str
    file_size: int
    uploaded_at: datetime
    updated_at: datetime
    is_starred: bool = False
    document_content: str | None = None
    spreadsheet_data: dict | None = None


class FileRename(BaseModel):
    original_name: str = Field(min_length=1, max_length=180)


class FileMove(BaseModel):
    folder_id: int | None = None


class FileStar(BaseModel):
    is_starred: bool


class FileCopy(BaseModel):
    """Destination for a file copy; omit for the My Files root."""

    folder_id: int | None = None


class FileBatch(BaseModel):
    """One action applied to several files - the select-all operations."""

    action: Literal["move", "copy", "trash", "star", "unstar"]
    file_ids: list[int] = Field(min_length=1, max_length=500)
    folder_id: int | None = None


class FileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    type: str = Field(default="word")
    folder_id: int | None = None


class FileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    type: str | None = None
    document_content: str | None = None
    spreadsheet_data: dict | None = None


class UploadResult(BaseModel):
    success: bool = True
    message: str
    uploaded: list[FileOut] = []
    failed: list[dict] = []
    storage_used: float = 0
    storage_limit: float = 0


class TrashOut(BaseModel):
    id: int
    file_id: int
    original_name: str
    file_type: str
    file_size: int
    deleted_at: datetime
    auto_delete: datetime


class ActivityOut(ORMModel):
    id: int
    user_id: int
    activity: str
    file_name: str | None
    ip_address: str | None
    activity_time: datetime


class ActivityWithUser(ActivityOut):
    user: UserBrief | None = None
