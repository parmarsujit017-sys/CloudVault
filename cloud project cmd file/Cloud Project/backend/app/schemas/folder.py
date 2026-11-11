from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class FolderCreate(BaseModel):
    folder_name: str = Field(min_length=1, max_length=180)
    parent_folder: int | None = None


class FolderUpdate(BaseModel):
    folder_name: str | None = Field(default=None, min_length=1, max_length=180)
    parent_folder: int | None = None


class FolderOut(ORMModel):
    id: int
    user_id: int
    folder_name: str
    parent_folder: int | None
    created_at: datetime
    file_count: int = 0
    subfolder_count: int = 0


class Crumb(BaseModel):
    id: int
    folder_name: str


class FolderCopy(BaseModel):
    """Destination for a folder copy; omit for the My Files root."""

    parent_folder: int | None = None


class FolderTreeCreate(BaseModel):
    """Materialise a set of relative directory paths in one round trip.

    The browser hands over every distinct directory it found inside a dropped or
    picked folder (`Photos`, `Photos/2024`, `Photos/2024/Trip`, ...) and gets
    back the folder id for each, so the files can then be uploaded straight into
    the right place.
    """

    parent_folder: int | None = None
    paths: list[str] = Field(default_factory=list, max_length=2000)


class FolderTreeResult(BaseModel):
    """`folders` is keyed by the cleaned path, which is what actually got made.

    `resolved` echoes back each path exactly as it was sent, so the uploader can
    look its own `webkitRelativePath` directories straight up without having to
    reimplement the server's name sanitising and risk the two drifting apart.
    """

    message: str
    created: int = 0
    folders: dict[str, int] = Field(default_factory=dict)
    resolved: dict[str, int] = Field(default_factory=dict)


class FolderBatch(BaseModel):
    """One action applied to several folders - the select-all operations."""

    action: Literal["move", "copy", "delete"]
    folder_ids: list[int] = Field(min_length=1, max_length=500)
    parent_folder: int | None = None


class BatchItemError(BaseModel):
    id: int
    name: str | None = None
    message: str


class BatchResult(BaseModel):
    success: bool = True
    message: str
    succeeded: list[int] = Field(default_factory=list)
    failed: list[BatchItemError] = Field(default_factory=list)


class FolderContents(BaseModel):
    folder: FolderOut | None
    breadcrumb: list[Crumb]
    folders: list[FolderOut]
    files: list["FileOut"]


from app.schemas.file import FileOut  # noqa: E402

FolderContents.model_rebuild()
