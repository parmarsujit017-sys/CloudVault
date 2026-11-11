from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Storage(Base):
    """Storage table (database specification, table 6). All values in MB."""

    __tablename__ = "storage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    total_storage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    used_storage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    available_storage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="storage")
