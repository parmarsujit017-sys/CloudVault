"""Administration: users, plans and plan assignment.

Every route here sits behind `get_current_admin`, so a normal account gets a
flat 403 rather than a partial view. The panel is read-mostly by design - the
one thing an administrator changes about somebody else's data is which plan
they are on, plus enabling or disabling the account.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import client_ip, get_current_admin
from app.config import settings
from app.database import get_db
from app.models import ActivityLog, File, Folder, FolderShare, FileShare, Plan, Subscription, Trash, User
from app.schemas.common import Message
from app.schemas.plan import (
    AdminStats,
    AdminUserDetail,
    AdminUserList,
    AdminUserOut,
    AdminUserUpdate,
    PlanAssign,
    PlanBreakdown,
    PlanCreate,
    PlanOut,
    PlanUpdate,
    SubscriptionOut,
)
from app.services import activity_service, plan_service, storage_service
from app.utils.files import sanitize_display_name

router = APIRouter(prefix="/api/admin", tags=["admin"])

PAGE_SIZE = 20
EXPIRING_SOON_DAYS = 7


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------


def _plan_out(db: Session, plan: Plan) -> PlanOut:
    data = PlanOut.model_validate(plan)
    data.feature_list = plan.feature_list
    data.subscriber_count = db.execute(
        select(func.count(Subscription.id)).where(
            Subscription.plan_id == plan.id, Subscription.status == "active"
        )
    ).scalar_one()
    return data


def _subscription_out(db: Session, record: Subscription) -> SubscriptionOut:
    data = SubscriptionOut.model_validate(record)
    plan = record.plan

    data.plan_name = plan.name if plan else None
    data.plan_code = plan.code if plan else None
    data.storage_mb = plan.storage_mb if plan else 0
    data.days_remaining = record.days_remaining
    data.is_expired = record.is_expired

    if plan is not None:
        data.price = plan.price_yearly if record.billing_cycle == "yearly" else plan.price_monthly
    if record.billing_cycle == "free":
        data.price = 0

    if record.assigned_by:
        granter = db.get(User, record.assigned_by)
        data.assigned_by_name = granter.fullname if granter else None

    return data


def _percent(used: float, limit: float) -> float:
    return round(used / limit * 100, 2) if limit else 0.0


def _user_out(db: Session, user: User, record: Subscription | None) -> AdminUserOut:
    data = AdminUserOut.model_validate(user)
    data.used_percent = _percent(user.storage_used, user.storage_limit)

    data.file_count = db.execute(
        select(func.count(File.id)).where(File.user_id == user.id, File.is_deleted.is_(False))
    ).scalar_one()
    data.folder_count = db.execute(
        select(func.count(Folder.id)).where(Folder.user_id == user.id)
    ).scalar_one()

    if record is not None and record.plan is not None:
        data.plan_name = record.plan.name
        data.plan_code = record.plan.code
        data.billing_cycle = record.billing_cycle
        data.plan_ends_at = record.ends_at
        data.plan_is_expired = record.is_expired

    return data


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=AdminStats, summary="Admin dashboard counters")
def stats(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Every figure is computed live; nothing here is cached or estimated."""
    total_users = db.execute(select(func.count(User.id))).scalar_one()
    active_users = db.execute(
        select(func.count(User.id)).where(User.status == "active")
    ).scalar_one()
    admin_users = db.execute(select(func.count(User.id)).where(User.role == "admin")).scalar_one()

    cutoff = datetime.utcnow() - timedelta(days=30)
    new_users = db.execute(
        select(func.count(User.id)).where(User.created_at >= cutoff)
    ).scalar_one()

    total_files = db.execute(
        select(func.count(File.id)).where(File.is_deleted.is_(False))
    ).scalar_one()
    total_folders = db.execute(select(func.count(Folder.id))).scalar_one()

    storage_used = db.execute(select(func.coalesce(func.sum(User.storage_used), 0))).scalar_one()
    storage_allocated = db.execute(
        select(func.coalesce(func.sum(User.storage_limit), 0))
    ).scalar_one()

    total_plans = db.execute(select(func.count(Plan.id))).scalar_one()
    active_plans = db.execute(
        select(func.count(Plan.id)).where(Plan.is_active.is_(True))
    ).scalar_one()

    subs = db.execute(
        select(Subscription).where(Subscription.status == "active")
    ).scalars().all()

    paid = [s for s in subs if s.plan is not None and not s.plan.is_free]
    free = [s for s in subs if s.plan is not None and s.plan.is_free]

    soon = datetime.utcnow() + timedelta(days=EXPIRING_SOON_DAYS)
    expiring = [s for s in paid if s.ends_at is not None and s.ends_at <= soon]

    # Monthly run rate: a yearly plan contributes a twelfth of its price.
    revenue = 0.0
    for record in paid:
        plan = record.plan
        if record.billing_cycle == "yearly":
            revenue += (plan.price_yearly or 0) / 12
        else:
            revenue += plan.price_monthly or 0

    breakdown: list[PlanBreakdown] = []
    for plan in db.execute(select(Plan).order_by(Plan.sort_order, Plan.id)).scalars().all():
        holders = [s.user_id for s in subs if s.plan_id == plan.id]
        used = 0.0
        if holders:
            used = db.execute(
                select(func.coalesce(func.sum(User.storage_used), 0)).where(User.id.in_(holders))
            ).scalar_one()
        breakdown.append(PlanBreakdown(
            plan_id=plan.id,
            name=plan.name,
            code=plan.code,
            subscribers=len(holders),
            storage_used=round(float(used), 4),
            is_free=plan.is_free,
        ))

    return AdminStats(
        total_users=total_users,
        active_users=active_users,
        disabled_users=total_users - active_users,
        admin_users=admin_users,
        new_users_30d=new_users,
        total_files=total_files,
        total_folders=total_folders,
        storage_used=round(float(storage_used), 4),
        storage_allocated=round(float(storage_allocated), 4),
        total_plans=total_plans,
        active_plans=active_plans,
        paid_subscribers=len(paid),
        free_subscribers=len(free),
        expiring_soon=len(expiring),
        monthly_revenue=round(revenue, 2),
        currency_symbol=settings.CURRENCY_SYMBOL,
        plan_breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@router.get("/users", response_model=AdminUserList, summary="List every user")
def list_users(
    q: str = Query(default="", description="Search name, username or email"),
    plan: str | None = Query(default=None, description="Filter by plan code"),
    account_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    stmt = select(User)

    term = q.strip().lower()
    if term:
        pattern = f"%{term}%"
        stmt = stmt.where(
            or_(
                func.lower(User.fullname).like(pattern),
                func.lower(User.username).like(pattern),
                func.lower(User.email).like(pattern),
            )
        )

    if account_status in ("active", "disabled"):
        stmt = stmt.where(User.status == account_status)

    rows = db.execute(stmt.order_by(User.created_at.desc(), User.id.desc())).scalars().all()

    # The current plan is a per-user lookup, so filter after resolving it.
    resolved = [(user, plan_service.active_subscription(db, user.id)) for user in rows]

    if plan:
        code = plan.strip().lower()
        resolved = [
            (user, sub) for user, sub in resolved
            if sub is not None and sub.plan is not None and sub.plan.code == code
        ]

    total = len(resolved)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, pages)
    window = resolved[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    return AdminUserList(
        total=total,
        page=page,
        pages=pages,
        users=[_user_out(db, user, sub) for user, sub in window],
    )


@router.get("/users/{user_id}", response_model=AdminUserDetail, summary="One user in full")
def user_detail(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    storage_service.sync_user_storage(db, user)
    current = plan_service.active_subscription(db, user.id)
    db.commit()

    base = _user_out(db, user, current)
    data = AdminUserDetail(**base.model_dump())

    history = db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.starts_at.desc(), Subscription.id.desc())
        .limit(20)
    ).scalars().all()
    data.history = [_subscription_out(db, record) for record in history]

    data.shared_out = db.execute(
        select(func.count(FileShare.id)).where(FileShare.shared_by == user.id)
    ).scalar_one() + db.execute(
        select(func.count(FolderShare.id)).where(FolderShare.shared_by == user.id)
    ).scalar_one()

    data.trash_count = db.execute(
        select(func.count(Trash.id)).where(Trash.user_id == user.id)
    ).scalar_one()

    data.last_active = db.execute(
        select(func.max(ActivityLog.activity_time)).where(ActivityLog.user_id == user.id)
    ).scalar_one()

    return data


@router.put("/users/{user_id}", response_model=AdminUserOut, summary="Update a user account")
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.fullname:
        user.fullname = sanitize_display_name(payload.fullname)

    if payload.status is not None:
        # Locking yourself out of the panel you are standing in is never the
        # intent, so it is refused rather than confirmed.
        if user.id == admin.id and payload.status != "active":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="You cannot disable your own account"
            )
        user.status = payload.status

    if payload.role is not None:
        if user.id == admin.id and payload.role != "admin":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin access"
            )
        if payload.role != "admin" and user.role == "admin":
            remaining = db.execute(
                select(func.count(User.id)).where(User.role == "admin", User.id != user.id)
            ).scalar_one()
            if not remaining:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail="There must be at least one administrator"
                )
        user.role = payload.role

    if payload.storage_limit is not None:
        # A manual override outside any plan; the next plan assignment wins.
        user.storage_limit = payload.storage_limit

    storage_service.sync_user_storage(db, user)
    activity_service.log(
        db, admin.id, activity_service.ADMIN_UPDATE_USER, user.username, client_ip(request)
    )
    db.commit()
    db.refresh(user)

    return _user_out(db, user, plan_service.active_subscription(db, user.id))


@router.delete("/users/{user_id}", response_model=Message, summary="Delete a user and their data")
def delete_user(
    user_id: int,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Removes the account, its files, folders, shares and stored bytes.

    Irreversible, which is why the panel asks the administrator to type the
    username before it calls this.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account"
        )

    if user.role == "admin":
        remaining = db.execute(
            select(func.count(User.id)).where(User.role == "admin", User.id != user.id)
        ).scalar_one()
        if not remaining:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="There must be at least one administrator"
            )

    username = user.username

    # Subscriptions reference plans with ON DELETE RESTRICT, so clear them first.
    for record in db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    ).scalars().all():
        db.delete(record)
    db.flush()

    from app.services.storage_backend import LocalStorageBackend, storage_backend

    db.delete(user)
    db.flush()

    if isinstance(storage_backend, LocalStorageBackend):
        storage_backend.purge_user(user_id)

    activity_service.log(
        db, admin.id, activity_service.ADMIN_DELETE_USER, username, client_ip(request)
    )
    db.commit()
    return Message(message=f"Account '{username}' and all of its data were deleted")


# ---------------------------------------------------------------------------
# Assigning plans
# ---------------------------------------------------------------------------


@router.post(
    "/users/{user_id}/subscription",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Put a user on a plan",
)
def assign_plan(
    user_id: int,
    payload: PlanAssign,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """The user's storage limit becomes the plan's allowance immediately."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    plan = plan_service.get_plan(db, payload.plan_id)

    record = plan_service.assign(
        db,
        user,
        plan,
        billing_cycle=payload.billing_cycle,
        months=payload.months,
        assigned_by=admin.id,
        note=payload.note,
        expires=payload.expires,
    )

    activity_service.log(
        db,
        admin.id,
        activity_service.ADMIN_ASSIGN_PLAN,
        f"{plan.name} -> {user.username}",
        client_ip(request),
    )
    # Recorded against the user too, so it shows up in their own activity feed.
    activity_service.log(db, user.id, activity_service.PLAN_CHANGED, plan.name, client_ip(request))

    db.commit()
    db.refresh(record)
    return _subscription_out(db, record)


@router.delete(
    "/users/{user_id}/subscription",
    response_model=SubscriptionOut,
    summary="Move a user back to the free plan",
)
def revoke_plan(
    user_id: int,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    default = plan_service.free_plan(db)
    if default is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="No free plan exists to fall back to"
        )

    record = plan_service.assign(
        db, user, default, "free", assigned_by=admin.id, note="Reverted to the free plan"
    )

    activity_service.log(
        db,
        admin.id,
        activity_service.ADMIN_ASSIGN_PLAN,
        f"{default.name} -> {user.username}",
        client_ip(request),
    )
    activity_service.log(
        db, user.id, activity_service.PLAN_CHANGED, default.name, client_ip(request)
    )

    db.commit()
    db.refresh(record)
    return _subscription_out(db, record)


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


def _slugify(value: str) -> str:
    out = "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out[:40] or "plan"


@router.get("/plans", response_model=list[PlanOut], summary="Every plan, retired ones included")
def list_plans(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Plan).order_by(Plan.sort_order, Plan.id)).scalars().all()
    return [_plan_out(db, plan) for plan in rows]


@router.post(
    "/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED, summary="Create a plan"
)
def create_plan(
    payload: PlanCreate,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    code = _slugify(payload.code or payload.name)

    if db.execute(select(Plan.id).where(Plan.code == code)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A plan with that code already exists")

    if payload.is_free:
        # Only one plan can be the automatic default, or new accounts would not
        # know which one they are on.
        for other in db.execute(select(Plan).where(Plan.is_free.is_(True))).scalars().all():
            other.is_free = False

    plan = Plan(
        code=code,
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        storage_mb=payload.storage_mb,
        price_monthly=payload.price_monthly,
        price_yearly=payload.price_yearly,
        is_free=payload.is_free,
        is_active=payload.is_active,
        features=payload.features,
        sort_order=payload.sort_order,
    )
    db.add(plan)
    db.flush()

    activity_service.log(
        db, admin.id, activity_service.ADMIN_CREATE_PLAN, plan.name, client_ip(request)
    )
    db.commit()
    db.refresh(plan)
    return _plan_out(db, plan)


@router.put("/plans/{plan_id}", response_model=PlanOut, summary="Edit a plan")
def update_plan(
    plan_id: int,
    payload: PlanUpdate,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Changing the allowance re-applies it to everybody currently on the plan,
    so the panel never shows a limit the subscribers are not actually getting."""
    plan = plan_service.get_plan(db, plan_id)
    fields = payload.model_fields_set

    if payload.name:
        plan.name = payload.name.strip()
    if "description" in fields:
        plan.description = (payload.description or "").strip() or None
    if payload.price_monthly is not None:
        plan.price_monthly = payload.price_monthly
    if payload.price_yearly is not None:
        plan.price_yearly = payload.price_yearly
    if "features" in fields:
        plan.features = payload.features
    if payload.sort_order is not None:
        plan.sort_order = payload.sort_order

    if payload.is_free is not None:
        if payload.is_free:
            for other in db.execute(
                select(Plan).where(Plan.is_free.is_(True), Plan.id != plan.id)
            ).scalars().all():
                other.is_free = False
        elif plan.is_free:
            remaining = db.execute(
                select(func.count(Plan.id)).where(Plan.is_free.is_(True), Plan.id != plan.id)
            ).scalar_one()
            if not remaining:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="One plan must stay the free default for new accounts",
                )
        plan.is_free = payload.is_free

    if payload.is_active is not None:
        if not payload.is_active and plan.is_free:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="The free default plan cannot be retired"
            )
        plan.is_active = payload.is_active

    limit_changed = payload.storage_mb is not None and payload.storage_mb != plan.storage_mb
    if payload.storage_mb is not None:
        plan.storage_mb = payload.storage_mb

    db.flush()

    if limit_changed:
        holders = db.execute(
            select(Subscription).where(
                Subscription.plan_id == plan.id, Subscription.status == "active"
            )
        ).scalars().all()
        for record in holders:
            subscriber = db.get(User, record.user_id)
            if subscriber is not None:
                plan_service.apply_limit(db, subscriber, plan)

    activity_service.log(
        db, admin.id, activity_service.ADMIN_UPDATE_PLAN, plan.name, client_ip(request)
    )
    db.commit()
    db.refresh(plan)
    return _plan_out(db, plan)


@router.delete("/plans/{plan_id}", response_model=Message, summary="Delete a plan")
def delete_plan(
    plan_id: int,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Refused while anybody is on it - retiring (`is_active=false`) is the way
    to withdraw a plan without disturbing its existing subscribers."""
    plan = plan_service.get_plan(db, plan_id)

    if plan.is_free:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="The free default plan cannot be deleted"
        )

    holders = db.execute(
        select(func.count(Subscription.id)).where(
            Subscription.plan_id == plan.id, Subscription.status == "active"
        )
    ).scalar_one()
    if holders:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"{holders} user(s) are on this plan. Move them first, "
                "or retire the plan instead of deleting it."
            ),
        )

    name = plan.name

    # Historical rows would block the delete, and they describe a plan that is
    # about to stop existing, so they go with it.
    for record in db.execute(
        select(Subscription).where(Subscription.plan_id == plan.id)
    ).scalars().all():
        db.delete(record)
    db.flush()

    db.delete(plan)
    activity_service.log(db, admin.id, activity_service.ADMIN_DELETE_PLAN, name, client_ip(request))
    db.commit()
    return Message(message=f"Plan '{name}' deleted")
