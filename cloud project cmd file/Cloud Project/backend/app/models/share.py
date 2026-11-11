from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FileShare(Base):
    """File Sharing table (database specification, table 5).

    share_link -> unique, unguessable URL token
    password   -> bcrypt hash of the optional link password (never plaintext)
    shared_to  -> target user id for a direct share, NULL for a public link
    permission -> "editor" (can edit) or "viewer" (read-only), default "viewer"
    """

    __tablename__ = "file_sharing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    share_link: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permission: Mapped[str] = mapped_column(String(32), default="viewer", nullable=False)
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    file = relationship("File", back_populates="shares")
    owner = relationship("User", foreign_keys=[shared_by])
    recipient = relationship("User", foreign_keys=[shared_to])

    @property
    def is_expired(self) -> bool:
        return self.expiry_date is not None and self.expiry_date < datetime.utcnow()


class FolderShare(Base):
    """Folder sharing (additive companion to `file_sharing`).

    A folder share grants access to the whole subtree rooted at `folder_id`:
    every descendant folder and every live file inside them. The columns mirror
    `file_sharing` exactly so both kinds of share behave the same way - direct
    share when `shared_to` is set, public link otherwise, with the same optional
    password and expiry.
    
    permission -> "editor" (can edit) or "viewer" (read-only), default "viewer"
    """

    __tablename__ = "folder_sharing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    share_link: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permission: Mapped[str] = mapped_column(String(32), default="viewer", nullable=False)
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    folder = relationship("Folder", back_populates="shares")
    owner = relationship("User", foreign_keys=[shared_by])
    recipient = relationship("User", foreign_keys=[shared_to])

    @property
    def is_expired(self) -> bool:
        return self.expiry_date is not None and self.expiry_date < datetime.utcnow()
