from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

BillingCycle = Literal["free", "monthly", "yearly"]


class PlanBase(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    storage_mb: float = Field(gt=0, le=100 * 1024 * 1024)  # up to 100 TB
    price_monthly: float = Field(default=0, ge=0, le=10_000_000)
    price_yearly: float = Field(default=0, ge=0, le=10_000_000)
    features: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0, le=999)


class PlanCreate(PlanBase):
    """`code` is the stable identifier; it is generated from the name if omitted."""

    code: str | None = Field(default=None, min_length=2, max_length=40)
    is_free: bool = False


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    storage_mb: float | None = Field(default=None, gt=0, le=100 * 1024 * 1024)
    price_monthly: float | None = Field(default=None, ge=0, le=10_000_000)
    price_yearly: float | None = Field(default=None, ge=0, le=10_000_000)
    features: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    is_free: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=999)


class PlanOut(ORMModel):
    id: int
    code: str
    name: str
    description: str | None
    storage_mb: float
    price_monthly: float
    price_yearly: float
    is_free: bool
    is_active: bool
    sort_order: int
    created_at: datetime
    feature_list: list[str] = []
    subscriber_count: int = 0


class SubscriptionOut(ORMModel):
    id: int
    user_id: int
    plan_id: int
    billing_cycle: str
    status: str
    starts_at: datetime
    ends_at: datetime | None
    note: str | None = None
    created_at: datetime
    plan_name: str | None = None
    plan_code: str | None = None
    storage_mb: float = 0
    price: float = 0
    days_remaining: int | None = None
    is_expired: bool = False
    assigned_by_name: str | None = None


class MyPlan(BaseModel):
    """What the "Your plan" panel renders."""

    plan: PlanOut | None = None
    subscription: SubscriptionOut | None = None
    storage_used: float = 0
    storage_limit: float = 0
    used_percent: float = 0
    currency_code: str = "INR"
    currency_symbol: str = "₹"


class PlanAssign(BaseModel):
    plan_id: int
    billing_cycle: BillingCycle = "monthly"
    months: int = Field(default=1, ge=1, le=120)
    expires: bool = True
    note: str | None = Field(default=None, max_length=255)


class AdminUserOut(ORMModel):
    """A user as the admin panel lists them: identity, usage and current plan."""

    id: int
    fullname: str
    username: str
    email: str
    role: str
    status: str
    profile_image: str | None = None
    storage_used: float
    storage_limit: float
    used_percent: float = 0
    created_at: datetime

    file_count: int = 0
    folder_count: int = 0

    plan_name: str | None = None
    plan_code: str | None = None
    billing_cycle: str | None = None
    plan_ends_at: datetime | None = None
    plan_is_expired: bool = False


class AdminUserDetail(AdminUserOut):
    history: list[SubscriptionOut] = []
    shared_out: int = 0
    trash_count: int = 0
    last_active: datetime | None = None


class AdminUserUpdate(BaseModel):
    fullname: str | None = Field(default=None, min_length=2, max_length=150)
    status: Literal["active", "disabled"] | None = None
    role: Literal["admin", "user"] | None = None
    storage_limit: float | None = Field(default=None, ge=0, le=100 * 1024 * 1024)


class AdminUserList(BaseModel):
    total: int
    page: int
    pages: int
    users: list[AdminUserOut] = []


class PlanBreakdown(BaseModel):
    plan_id: int
    name: str
    code: str
    subscribers: int
    storage_used: float
    is_free: bool


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    disabled_users: int
    admin_users: int
    new_users_30d: int

    total_files: int
    total_folders: int
    storage_used: float
    storage_allocated: float

    total_plans: int
    active_plans: int
    paid_subscribers: int
    free_subscribers: int
    expiring_soon: int

    monthly_revenue: float = 0
    currency_symbol: str = "₹"

    plan_breakdown: list[PlanBreakdown] = []
