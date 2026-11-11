from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Folder(Base):
    """Folders table (database specification, table 2). Supports nesting via
    parent_folder -> folders.id."""

    __tablename__ = "folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_folder: Mapped[int | None] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    owner = relationship("User", back_populates="folders")
    parent = relationship("Folder", back_populates="children", remote_side=[id])
    children = relationship("Folder", back_populates="parent", cascade="all, delete-orphan")
    files = relationship("File", back_populates="folder")
    shares = relationship("FolderShare", back_populates="folder", cascade="all, delete-orphan")
