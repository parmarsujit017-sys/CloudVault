"""Plans, subscriptions, and the bootstrap that makes /admin reachable.

The rule that ties this to the rest of the app is deliberately narrow: a
subscription decides a user's `storage_limit`, and nothing else. Every quota
check, the storage ring, the dashboard and the upload guard all keep reading
`storage_limit` exactly as they did before plans existed.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.config import settings
from app.models import Plan, Setting, Subscription, User
from app.services import storage_service

MONTH_DAYS = 30
YEAR_DAYS = 365

CYCLES = ("free", "monthly", "yearly")


# ---------------------------------------------------------------------------
# The catalogue shipped on an empty database
# ---------------------------------------------------------------------------

DEFAULT_PLANS = [
    {
        "code": "free",
        "name": "Free",
        "description": "Everything you need to get started.",
        "storage_mb": 25 * 1024,
        "price_monthly": 0.0,
        "price_yearly": 0.0,
        "is_free": True,
        "sort_order": 1,
        "features": (
            "25 GB of storage\n"
            "Upload whole folders\n"
            "Share files and folders by link\n"
            "30-day Trash recovery"
        ),
    },
    {
        "code": "personal",
        "name": "Personal",
        "description": "For one person with a lot to keep.",
        "storage_mb": 200 * 1024,
        "price_monthly": 149.0,
        "price_yearly": 1490.0,
        "is_free": False,
        "sort_order": 2,
        "features": (
            "200 GB of storage\n"
            "Everything in Free\n"
            "Password-protected share links\n"
            "Link expiry dates\n"
            "Two months free on yearly billing"
        ),
    },
    {
        "code": "professional",
        "name": "Professional",
        "description": "For heavy day-to-day use.",
        "storage_mb": 2 * 1024 * 1024,
        "price_monthly": 499.0,
        "price_yearly": 4990.0,
        "is_free": False,
        "sort_order": 3,
        "features": (
            "2 TB of storage\n"
            "Everything in Personal\n"
            "Priority upload bandwidth\n"
            "Extended activity history\n"
            "Two months free on yearly billing"
        ),
    },
    {
        "code": "business",
        "name": "Business",
        "description": "For a team working out of one drive.",
        "storage_mb": 5 * 1024 * 1024,
        "price_monthly": 1299.0,
        "price_yearly": 12990.0,
        "is_free": False,
        "sort_order": 4,
        "features": (
            "5 TB of storage\n"
            "Everything in Professional\n"
            "Unlimited folder sharing\n"
            "Full audit trail\n"
            "Two months free on yearly billing"
        ),
    },
]


def free_plan(db: Session) -> Plan | None:
    """The plan new accounts land on. There is only ever meant to be one."""
    return db.execute(
        select(Plan).where(Plan.is_free.is_(True)).order_by(Plan.sort_order, Plan.id)
    ).scalars().first()


def get_plan(db: Session, plan_id: int) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


def seed_catalogue(db: Session) -> int:
    """Create the default plans, once, on an empty catalogue.

    It only ever adds plans that are missing by code, so an administrator can
    edit or delete the shipped ones without them reappearing wholesale on the
    next restart.
    """
    existing = db.execute(select(func.count(Plan.id))).scalar_one()
    if existing:
        return 0

    for spec in DEFAULT_PLANS:
        db.add(Plan(**spec))
    db.flush()
    return len(DEFAULT_PLANS)


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


def active_subscription(db: Session, user_id: int) -> Subscription | None:
    return db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status == "active")
        .order_by(Subscription.starts_at.desc(), Subscription.id.desc())
    ).scalars().first()


def period_end(cycle: str, start: datetime, months: int | None = None) -> datetime | None:
    """When a cycle that starts at `start` runs out. Free plans never do."""
    if cycle == "free":
        return None
    if cycle == "yearly":
        return start + timedelta(days=YEAR_DAYS * (months or 1))
    return start + timedelta(days=MONTH_DAYS * (months or 1))


def apply_limit(db: Session, user: User, plan: Plan) -> None:
    """A plan's allowance *is* the user's storage limit."""
    user.storage_limit = float(plan.storage_mb)
    storage_service.sync_user_storage(db, user)


def assign(
    db: Session,
    user: User,
    plan: Plan,
    billing_cycle: str = "free",
    months: int = 1,
    assigned_by: int | None = None,
    note: str | None = None,
    expires: bool = True,
) -> Subscription:
    """Put `user` on `plan`, superseding whatever they were on before.

    `expires=False` grants the plan with no end date, which is what a comped or
    internal account wants - and what the administrator's own account uses.
    """
    if billing_cycle not in CYCLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown billing cycle")

    if plan.is_free:
        billing_cycle = "free"
    elif billing_cycle == "free":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Choose monthly or yearly billing for a paid plan",
        )

    if not plan.is_active:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="That plan is retired and cannot be assigned"
        )

    current = active_subscription(db, user.id)
    if current is not None:
        current.status = "replaced"

    now = datetime.utcnow()
    record = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        billing_cycle=billing_cycle,
        status="active",
        starts_at=now,
        ends_at=period_end(billing_cycle, now, months) if expires else None,
        assigned_by=assigned_by,
        note=note,
    )
    db.add(record)
    db.flush()

    apply_limit(db, user, plan)
    return record


def ensure_subscription(db: Session, user: User) -> Subscription | None:
    """Guarantee the user is on *some* plan, and that it has not run out.

    Called on the paths that read a user's allowance, so an expired paid plan
    quietly falls back to Free rather than leaving a user on storage they are
    no longer entitled to. Downgrading never deletes anything - the account just
    stops being able to upload more until they are under the free allowance.
    """
    current = active_subscription(db, user.id)

    if current is not None and not current.is_expired:
        # Keep the limit honest if an admin edited the plan underneath them.
        if current.plan is not None and user.storage_limit != current.plan.storage_mb:
            apply_limit(db, user, current.plan)
        return current

    default = free_plan(db)
    if default is None:
        return current

    if current is not None:
        current.status = "expired"

    return assign(db, user, default, "free", note="Automatic free plan")


def backfill_subscriptions(db: Session) -> int:
    """Put every user without an active subscription on the free plan.

    Accounts created before plans existed have none, and `ensure_subscription`
    would only reach them the next time they signed in - leaving the admin
    overview counting fewer subscribers than it has users. Running this once at
    startup makes the data match what the panel claims.
    """
    default = free_plan(db)
    if default is None:
        return 0

    subscribed = set(
        db.execute(
            select(Subscription.user_id).where(Subscription.status == "active")
        ).scalars().all()
    )

    stmt = select(User)
    if subscribed:
        stmt = stmt.where(User.id.notin_(subscribed))
    missing = db.execute(stmt).scalars().all()

    for user in missing:
        assign(db, user, default, "free", note="Automatic free plan")

    return len(missing)


def usage_summary(db: Session, user: User) -> dict:
    """Everything the "Your plan" panel needs, in one shape."""
    record = ensure_subscription(db, user)
    plan = record.plan if record else None

    return {
        "plan": plan,
        "subscription": record,
        "storage_used": user.storage_used,
        "storage_limit": user.storage_limit,
    }


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def ensure_admin(db: Session) -> User | None:
    """Create the configured administrator if the database has none.

    Without this a fresh deployment has no way into /admin. It is keyed on the
    configured username, and it never rewrites an existing account's password -
    so changing ADMIN_PASSWORD in .env does not silently reset a live admin.
    """
    username = (settings.ADMIN_USERNAME or "").strip().lower()
    if not username:
        return None

    existing = db.execute(
        select(User).where(func.lower(User.username) == username)
    ).scalar_one_or_none()

    if existing is not None:
        # Make sure the account can still actually administer.
        if existing.role != "admin":
            existing.role = "admin"
        if existing.status != "active":
            existing.status = "active"
        db.flush()
        return existing

    admin = User(
        fullname=settings.ADMIN_FULLNAME,
        username=username,
        email=settings.ADMIN_EMAIL.strip().lower(),
        password=hash_password(settings.ADMIN_PASSWORD),
        role="admin",
        storage_limit=float(settings.DEFAULT_STORAGE_LIMIT_MB),
        status="active",
    )
    db.add(admin)
    db.flush()

    if db.execute(select(Setting).where(Setting.user_id == admin.id)).scalar_one_or_none() is None:
        db.add(Setting(user_id=admin.id))

    storage_service.sync_user_storage(db, admin)
    db.flush()
    return admin


def grant_admin_allowance(db: Session, admin: User) -> None:
    """Put the administrator on the largest plan, with no end date.

    An admin left on the automatic Free plan would run out of room managing the
    very system they administer, and nobody exists to grant them anything.
    """
    if active_subscription(db, admin.id) is not None:
        return

    biggest = db.execute(
        select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.storage_mb.desc())
    ).scalars().first()
    if biggest is None:
        return

    assign(
        db,
        admin,
        biggest,
        billing_cycle="free" if biggest.is_free else "yearly",
        expires=False,
        note="Administrator account",
    )
