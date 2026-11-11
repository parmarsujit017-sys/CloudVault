from pydantic import BaseModel

from app.schemas.file import ActivityOut, FileOut
from app.schemas.share import ShareOut


class StorageOut(BaseModel):
    total_storage: float
    used_storage: float
    available_storage: float
    used_percent: float


class DashboardOut(BaseModel):
    total_files: int
    total_folders: int
    storage_used: float
    storage_limit: float
    available_storage: float
    used_percent: float
    shared_files: int
    trash_files: int
    recent_files: list[FileOut] = []
    recent_activity: list[ActivityOut] = []


class SearchResults(BaseModel):
    query: str
    files: list[FileOut] = []
    folders: list[dict] = []
    shared: list[ShareOut] = []
