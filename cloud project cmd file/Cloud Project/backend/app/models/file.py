from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class File(Base):
    """Files table (database specification, table 3).

    file_name     -> generated system name actually written to disk (UUID based)
    original_name -> the name the user uploaded and sees
    file_path     -> path on the storage backend, relative to UPLOAD_DIR
    file_size     -> size in BYTES (aggregated into MB for Users/Storage tables)

    is_deleted and is_starred are additive columns (documented in the README)
    used to flag trashed and starred files without adding new tables.
    """

    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="file", nullable=False, index=True)
    file_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    document_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    spreadsheet_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    owner = relationship("User", back_populates="files")
    folder = relationship("Folder", back_populates="files")
    trash = relationship("Trash", back_populates="file", cascade="all, delete-orphan", uselist=False)
    shares = relationship("FileShare", back_populates="file", cascade="all, delete-orphan")

    @property
    def type(self) -> str:
        return self.kind
