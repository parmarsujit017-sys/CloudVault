"""What a signed-in user can see about plans: the catalogue, and their own.

Users cannot change their plan here. Assignment is an administrator action, so
this side of it is read-only by design - the panel tells you what you are on and
what else exists, and points you at the administrator to change it.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Plan, Subscription, User
from app.schemas.plan import MyPlan, PlanOut, SubscriptionOut
from app.services import plan_service, storage_service

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _plan_out(plan: Plan) -> PlanOut:
    data = PlanOut.model_validate(plan)
    data.feature_list = plan.feature_list
    return data


def _subscription_out(db: Session, record: Subscription) -> SubscriptionOut:
    data = SubscriptionOut.model_validate(record)
    plan = record.plan

    data.plan_name = plan.name if plan else None
    data.plan_code = plan.code if plan else None
    data.storage_mb = plan.storage_mb if plan else 0
    data.days_remaining = record.days_remaining
    data.is_expired = record.is_expired

    if plan is not None and record.billing_cycle != "free":
        data.price = plan.price_yearly if record.billing_cycle == "yearly" else plan.price_monthly

    if record.assigned_by:
        granter = db.get(User, record.assigned_by)
        data.assigned_by_name = granter.fullname if granter else None

    return data


@router.get("", response_model=list[PlanOut], summary="The plan catalogue")
def list_plans(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Active plans only - retired ones stay hidden from users while their
    existing subscribers keep them."""
    rows = db.execute(
        select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order, Plan.id)
    ).scalars().all()
    return [_plan_out(plan) for plan in rows]


@router.get("/me", response_model=MyPlan, summary="The current user's plan")
def my_plan(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    storage_service.sync_user_storage(db, user)
    record = plan_service.ensure_subscription(db, user)
    db.commit()
    db.refresh(user)

    percent = (user.storage_used / user.storage_limit * 100) if user.storage_limit else 0.0

    return MyPlan(
        plan=_plan_out(record.plan) if record and record.plan else None,
        subscription=_subscription_out(db, record) if record else None,
        storage_used=round(user.storage_used, 4),
        storage_limit=round(user.storage_limit, 4),
        used_percent=round(percent, 2),
        currency_code=settings.CURRENCY_CODE,
        currency_symbol=settings.CURRENCY_SYMBOL,
    )


@router.get("/me/history", response_model=list[SubscriptionOut], summary="Your plan history")
def my_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.starts_at.desc(), Subscription.id.desc())
        .limit(25)
    ).scalars().all()
    return [_subscription_out(db, record) for record in rows]
