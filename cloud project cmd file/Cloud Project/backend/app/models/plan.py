from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Plan(Base):
    """A storage package an administrator can assign to a user.

    Prices are recorded for display only - this application does not process
    payments. What it does own is the *allowance*: assigning a plan is what sets
    a user's `storage_limit`, so every quota check already in the app keeps
    working without knowing plans exist at all.
    """

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    storage_mb: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price_monthly: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price_yearly: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Exactly one plan is the free default new accounts land on.
    is_free: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # One feature per line; the UI splits them into a bullet list.
    features: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    subscriptions = relationship("Subscription", back_populates="plan")

    @property
    def feature_list(self) -> list[str]:
        return [line.strip() for line in (self.features or "").splitlines() if line.strip()]


class Subscription(Base):
    """One assignment of a plan to a user.

    Assignments are never overwritten: a new one supersedes the last, which is
    kept with status `replaced`. That history is what lets the admin panel show
    what a user was on before, and when it changed.
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # free plans never expire, so they carry the cycle "free" and no end date.
    billing_cycle: Mapped[str] = mapped_column(String(10), default="free", nullable=False)
    status: Mapped[str] = mapped_column(String(12), default="active", nullable=False, index=True)

    starts_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Which administrator granted it; NULL for the automatic free plan.
    assigned_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="subscriptions", foreign_keys=[user_id])
    plan = relationship("Plan", back_populates="subscriptions")
    granted_by = relationship("User", foreign_keys=[assigned_by])

    @property
    def is_expired(self) -> bool:
        return self.ends_at is not None and self.ends_at < datetime.utcnow()

    @property
    def days_remaining(self) -> int | None:
        if self.ends_at is None:
            return None
        return max(0, (self.ends_at - datetime.utcnow()).days)
