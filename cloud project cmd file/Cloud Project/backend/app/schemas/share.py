from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class ShareCreate(BaseModel):
    """Create either a direct user share or a public link.

    Provide `shared_to_username` (or `shared_to`) for a user share; omit both
    for a public link.
    
    permission: "editor" (can edit) or "viewer" (read-only), default "viewer"
    """

    file_id: int
    shared_to: int | None = None
    shared_to_username: str | None = Field(default=None, max_length=160)
    password: str | None = Field(default=None, min_length=4, max_length=72)
    permission: str = Field(default="viewer", pattern="^(editor|viewer)$")
    expiry_date: datetime | None = None

    @model_validator(mode="after")
    def normalise(self):
        if self.shared_to_username is not None:
            self.shared_to_username = self.shared_to_username.strip() or None
        if self.password is not None and not self.password.strip():
            self.password = None
        return self


class FolderShareCreate(BaseModel):
    """Share a whole folder: its subfolders and every file inside them.
    
    permission: "editor" (can edit) or "viewer" (read-only), default "viewer"
    """

    folder_id: int
    shared_to: int | None = None
    shared_to_username: str | None = Field(default=None, max_length=160)
    password: str | None = Field(default=None, min_length=4, max_length=72)
    permission: str = Field(default="viewer", pattern="^(editor|viewer)$")
    expiry_date: datetime | None = None

    @model_validator(mode="after")
    def normalise(self):
        if self.shared_to_username is not None:
            self.shared_to_username = self.shared_to_username.strip() or None
        if self.password is not None and not self.password.strip():
            self.password = None
        return self


class ShareOut(ORMModel):
    id: int
    kind: Literal["file", "folder"] = "file"
    file_id: int | None = None
    folder_id: int | None = None
    shared_by: int
    shared_to: int | None
    share_link: str
    permission: str = "viewer"
    has_password: bool = False
    expiry_date: datetime | None
    created_at: datetime
    file_name: str | None = None
    file_type: str | None = None
    file_size: int | None = None
    file_kind: str | None = None
    folder_name: str | None = None
    item_count: int = 0
    shared_by_name: str | None = None
    shared_to_name: str | None = None
    share_url: str | None = None
    is_expired: bool = False


class SharePasswordCheck(BaseModel):
    password: str = Field(min_length=1, max_length=72)


class SharePublicInfo(BaseModel):
    kind: Literal["file", "folder"] = "file"
    file_name: str
    file_type: str
    file_size: int
    shared_by_name: str
    created_at: datetime
    expiry_date: datetime | None
    requires_password: bool
    is_expired: bool = False
    item_count: int = 0
    folder_count: int = 0


class SharedEntry(BaseModel):
    """One row inside a publicly shared folder.

    `path` is relative to the share root, which is what lets the browser rebuild
    the original folder structure without ever learning real folder ids.
    """

    kind: Literal["file", "folder"]
    name: str
    path: str
    file_id: int | None = None
    file_type: str | None = None
    file_size: int | None = None
    file_kind: str | None = None
    updated_at: datetime | None = None
    item_count: int = 0


class SharedFolderListing(BaseModel):
    folder_name: str
    path: str
    breadcrumb: list[str] = Field(default_factory=list)
    entries: list[SharedEntry] = Field(default_factory=list)
