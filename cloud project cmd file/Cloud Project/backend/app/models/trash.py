from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Trash(Base):
    """Trash table (database specification, table 4)."""

    __tablename__ = "trash"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    auto_delete: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    file = relationship("File", back_populates="trash")
