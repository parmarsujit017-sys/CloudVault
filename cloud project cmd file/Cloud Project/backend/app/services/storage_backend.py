"""Pluggable storage backend.

Only `LocalStorageBackend` ships today, but every read/write in the app goes
through this interface so an S3 / R2 / Cloudinary backend can be dropped in
later without touching the routers.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

from app.config import settings
from app.utils.files import ensure_within


class StorageBackend(ABC):
    @abstractmethod
    def save(self, relative_path: str, stream: BinaryIO, max_bytes: int) -> int:
        """Persist a stream and return the number of bytes written."""

    @abstractmethod
    def open(self, relative_path: str) -> BinaryIO: ...

    @abstractmethod
    def delete(self, relative_path: str) -> None: ...

    @abstractmethod
    def exists(self, relative_path: str) -> bool: ...

    @abstractmethod
    def absolute(self, relative_path: str) -> Path: ...


class LocalStorageBackend(StorageBackend):
    """Stores files under UPLOAD_DIR/users/<user_id>/files/<uuid>.<ext>."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or settings.upload_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative_path: str) -> Path:
        # Guards against `..` segments or absolute paths sneaking in from the DB.
        return ensure_within(self.root, Path(relative_path))

    @staticmethod
    def build_path(user_id: int, stored_name: str) -> str:
        return f"users/{user_id}/files/{stored_name}"

    def save(self, relative_path: str, stream: BinaryIO, max_bytes: int) -> int:
        target = self._resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        try:
            with target.open("wb") as out:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if max_bytes and written > max_bytes:
                        raise ValueError("FILE_TOO_LARGE")
                    out.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return written

    def open(self, relative_path: str) -> BinaryIO:
        return self._resolve(relative_path).open("rb")

    def delete(self, relative_path: str) -> None:
        try:
            self._resolve(relative_path).unlink(missing_ok=True)
        except ValueError:
            pass

    def exists(self, relative_path: str) -> bool:
        try:
            return self._resolve(relative_path).is_file()
        except ValueError:
            return False

    def absolute(self, relative_path: str) -> Path:
        return self._resolve(relative_path)

    def purge_user(self, user_id: int) -> None:
        shutil.rmtree(self.root / "users" / str(user_id), ignore_errors=True)


storage_backend: StorageBackend = LocalStorageBackend()
