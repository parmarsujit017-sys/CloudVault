from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """Users table (database specification, table 1).

    storage_used / storage_limit are stored in MEGABYTES, as required by the
    specification. They are floats so that files smaller than 1 MB are still
    accounted for accurately.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fullname: Mapped[str] = mapped_column(String(150), nullable=False)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)  # bcrypt hash only
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)  # admin | user
    profile_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_used: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    storage_limit: Mapped[float] = mapped_column(Float, default=25600.0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active | disabled
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    folders = relationship("Folder", back_populates="owner", cascade="all, delete-orphan")
    files = relationship("File", back_populates="owner", cascade="all, delete-orphan")
    storage = relationship(
        "Storage", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    settings = relationship(
        "Setting", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    activities = relationship("ActivityLog", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship(
        "Subscription",
        back_populates="user",
        foreign_keys="Subscription.user_id",
        cascade="all, delete-orphan",
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
