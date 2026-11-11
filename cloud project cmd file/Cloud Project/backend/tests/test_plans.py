"""The plan catalogue and what a user can see of their own subscription."""

import pytest


@pytest.fixture(scope="module")
def grace(client):
    from tests.conftest import Actor

    return Actor(client, "grace")


def test_the_default_catalogue_is_seeded(grace):
    plans = grace.get("/api/plans").json()
    codes = [plan["code"] for plan in plans]

    assert "free" in codes
    assert len(plans) >= 2, "there should be something to upgrade to"

    free = next(plan for plan in plans if plan["code"] == "free")
    assert free["is_free"] is True
    assert free["storage_mb"] == 25 * 1024
    assert free["price_monthly"] == 0
    assert free["feature_list"], "plans carry a feature list for the pricing cards"


def test_exactly_one_plan_is_the_free_default(grace):
    plans = grace.get("/api/plans").json()
    assert len([plan for plan in plans if plan["is_free"]]) == 1


def test_priced_plans_are_cheaper_yearly_than_twelve_months(grace):
    """The yearly price is meant to be a discount, not the same number x12."""
    priced = [p for p in grace.get("/api/plans").json() if p["price_monthly"] > 0]
    assert priced

    for plan in priced:
        assert plan["price_yearly"] < plan["price_monthly"] * 12, plan["name"]


def test_a_new_account_is_on_the_free_plan_with_the_free_allowance(grace):
    body = grace.get("/api/plans/me").json()

    assert body["plan"]["code"] == "free"
    assert body["subscription"]["status"] == "active"
    assert body["subscription"]["billing_cycle"] == "free"
    assert body["storage_limit"] == 25 * 1024

    # The plan is what the rest of the app measures against.
    assert grace.get("/api/storage").json()["total_storage"] == 25 * 1024


def test_the_plan_shows_up_in_history(grace):
    history = grace.get("/api/plans/me/history").json()
    assert history
    assert history[0]["plan_code"] == "free"


def test_plans_need_a_signed_in_user(client):
    assert client.get("/api/plans").status_code == 401
    assert client.get("/api/plans/me").status_code == 401


def test_a_user_cannot_reach_any_admin_endpoint(grace):
    """The panel is signposting; this is the actual boundary."""
    assert grace.get("/api/admin/stats").status_code == 403
    assert grace.get("/api/admin/users").status_code == 403
    assert grace.get("/api/admin/plans").status_code == 403
    assert grace.post("/api/admin/plans", json={
        "name": "Sneaky", "storage_mb": 999999
    }).status_code == 403
    assert grace.post(
        f"/api/admin/users/{grace.id}/subscription", json={"plan_id": 1}
    ).status_code == 403


def test_anonymous_callers_cannot_reach_admin_endpoints(client):
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/api/admin/users").status_code == 401


def test_backfill_puts_pre_plan_accounts_on_the_free_plan(client, grace):
    """Accounts created before plans existed have no subscription at all.

    They would otherwise stay uncounted until their owner next signed in, which
    makes every figure in the admin panel disagree with the user list.
    """
    from app.database import SessionLocal
    from app.models import Subscription, User
    from app.services import plan_service

    db = SessionLocal()
    try:
        user = db.get(User, grace.id)

        # Rewind this account to how a pre-plan one looks.
        for record in db.query(Subscription).filter(Subscription.user_id == user.id).all():
            db.delete(record)
        user.storage_limit = 15360.0
        db.commit()

        assert plan_service.active_subscription(db, user.id) is None

        moved = plan_service.backfill_subscriptions(db)
        db.commit()

        assert moved >= 1
        record = plan_service.active_subscription(db, user.id)
        assert record is not None
        assert record.plan.is_free is True

        # The allowance was corrected too, not just the bookkeeping.
        db.refresh(user)
        assert user.storage_limit == 25 * 1024
    finally:
        db.close()

    assert grace.get("/api/plans/me").json()["plan"]["is_free"] is True


def test_backfill_leaves_existing_subscriptions_alone(client, admin):
    from app.database import SessionLocal
    from app.services import plan_service

    db = SessionLocal()
    try:
        before = plan_service.active_subscription(db, admin.id)
        assert before is not None

        assert plan_service.backfill_subscriptions(db) == 0
        assert plan_service.active_subscription(db, admin.id).id == before.id
    finally:
        db.close()
