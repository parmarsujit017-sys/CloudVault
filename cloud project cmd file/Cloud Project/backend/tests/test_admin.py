"""The admin panel: users, plan management and assignment."""

import pytest


@pytest.fixture(scope="module")
def henry(client):
    """A plain user for the administrator to act on."""
    from tests.conftest import Actor

    return Actor(client, "henry")


@pytest.fixture(scope="module")
def paid_plan(admin):
    """The first non-free plan in the catalogue."""
    plans = admin.get("/api/admin/plans").json()
    return next(plan for plan in plans if not plan["is_free"])


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def test_stats_report_live_figures(admin, henry):
    body = admin.get("/api/admin/stats").json()

    assert body["total_users"] >= 2
    assert body["active_users"] <= body["total_users"]
    assert body["admin_users"] >= 1
    assert body["total_plans"] >= 2
    assert body["currency_symbol"]

    # Every user is on some plan, so the two subscriber counts cover everybody.
    assert body["paid_subscribers"] + body["free_subscribers"] == body["total_users"]
    assert [row["code"] for row in body["plan_breakdown"]]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def test_user_list_shows_storage_and_plan(admin, henry):
    body = admin.get("/api/admin/users?q=henry").json()
    assert body["total"] == 1

    row = body["users"][0]
    assert row["username"] == "henry"
    assert row["email"] == "henry@example.com"
    assert row["plan_name"]
    assert row["billing_cycle"] == "free"
    assert row["storage_limit"] == 25 * 1024
    assert row["used_percent"] >= 0


def test_user_search_matches_name_username_and_email(admin, henry):
    for term in ("henry", "Henry Tester", "henry@example.com"):
        found = admin.get(f"/api/admin/users?q={term}").json()
        assert any(u["username"] == "henry" for u in found["users"]), term

    assert admin.get("/api/admin/users?q=zzznobody").json()["total"] == 0


def test_user_detail_includes_history_and_counts(admin, henry):
    henry.upload("admin-visible.txt", b"hello")

    body = admin.get(f"/api/admin/users/{henry.id}").json()
    assert body["username"] == "henry"
    assert body["file_count"] >= 1
    assert body["history"], "the automatic free plan is part of the history"
    assert body["history"][0]["status"] == "active"


def test_unknown_user_is_a_404(admin):
    assert admin.get("/api/admin/users/999999").status_code == 404


# ---------------------------------------------------------------------------
# Assigning plans
# ---------------------------------------------------------------------------


def test_assigning_a_plan_raises_the_storage_limit_immediately(admin, henry, paid_plan):
    res = admin.post(
        f"/api/admin/users/{henry.id}/subscription",
        json={"plan_id": paid_plan["id"], "billing_cycle": "monthly", "months": 1},
    )
    assert res.status_code == 201, res.text
    record = res.json()

    assert record["plan_id"] == paid_plan["id"]
    assert record["billing_cycle"] == "monthly"
    assert record["status"] == "active"
    assert record["ends_at"] is not None
    assert record["assigned_by_name"]

    # The user sees it, and the quota really moved.
    mine = henry.get("/api/plans/me").json()
    assert mine["plan"]["id"] == paid_plan["id"]
    assert mine["storage_limit"] == paid_plan["storage_mb"]
    assert henry.get("/api/storage").json()["total_storage"] == paid_plan["storage_mb"]


def test_the_previous_subscription_is_superseded_not_duplicated(admin, henry):
    history = henry.get("/api/plans/me/history").json()

    assert len([record for record in history if record["status"] == "active"]) == 1
    assert any(record["status"] == "replaced" for record in history)


def test_yearly_billing_is_priced_and_dated_as_a_year(admin, henry, paid_plan):
    res = admin.post(
        f"/api/admin/users/{henry.id}/subscription",
        json={"plan_id": paid_plan["id"], "billing_cycle": "yearly", "months": 1},
    )
    assert res.status_code == 201
    record = res.json()

    assert record["billing_cycle"] == "yearly"
    assert record["price"] == paid_plan["price_yearly"]
    assert record["days_remaining"] > 300


def test_a_grant_can_be_made_with_no_end_date(admin, henry, paid_plan):
    record = admin.post(
        f"/api/admin/users/{henry.id}/subscription",
        json={
            "plan_id": paid_plan["id"],
            "billing_cycle": "monthly",
            "expires": False,
            "note": "Comped",
        },
    ).json()

    assert record["ends_at"] is None
    assert record["days_remaining"] is None
    assert record["note"] == "Comped"


def test_a_paid_plan_cannot_be_assigned_as_free(admin, henry, paid_plan):
    res = admin.post(
        f"/api/admin/users/{henry.id}/subscription",
        json={"plan_id": paid_plan["id"], "billing_cycle": "free"},
    )
    assert res.status_code == 400
    assert "monthly or yearly" in res.json()["message"]


def test_reverting_puts_the_user_back_on_free(admin, henry):
    res = admin.delete(f"/api/admin/users/{henry.id}/subscription")
    assert res.status_code == 200
    assert res.json()["billing_cycle"] == "free"

    mine = henry.get("/api/plans/me").json()
    assert mine["plan"]["is_free"] is True
    assert mine["storage_limit"] == 25 * 1024


def test_assigning_an_unknown_plan_is_a_404(admin, henry):
    res = admin.post(
        f"/api/admin/users/{henry.id}/subscription",
        json={"plan_id": 999999, "billing_cycle": "monthly"},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Managing accounts
# ---------------------------------------------------------------------------


def test_disabling_an_account_locks_the_user_out(admin, client, henry):
    assert admin.put(f"/api/admin/users/{henry.id}", json={"status": "disabled"}).status_code == 200

    # Existing tokens stop working, and so does signing in again.
    assert henry.get("/api/files").status_code == 403
    assert client.post(
        "/api/auth/login", json={"username": "henry", "password": henry.password}
    ).status_code == 403

    assert admin.put(f"/api/admin/users/{henry.id}", json={"status": "active"}).status_code == 200
    assert henry.get("/api/files").status_code == 200


def test_an_admin_cannot_lock_themselves_out(admin):
    assert admin.put(f"/api/admin/users/{admin.id}", json={"status": "disabled"}).status_code == 400
    assert admin.put(f"/api/admin/users/{admin.id}", json={"role": "user"}).status_code == 400
    assert admin.delete(f"/api/admin/users/{admin.id}").status_code == 400


def test_admin_access_can_be_granted_and_taken_back(admin, henry):
    assert admin.put(f"/api/admin/users/{henry.id}", json={"role": "admin"}).status_code == 200
    assert henry.get("/api/admin/stats").status_code == 200

    assert admin.put(f"/api/admin/users/{henry.id}", json={"role": "user"}).status_code == 200
    assert henry.get("/api/admin/stats").status_code == 403


def test_deleting_a_user_removes_their_files(admin, client):
    from tests.conftest import Actor

    doomed = Actor(client, "doomed")
    record = doomed.upload("gone.txt", b"bytes").json()["uploaded"][0]

    res = admin.delete(f"/api/admin/users/{doomed.id}")
    assert res.status_code == 200, res.text

    assert admin.get(f"/api/admin/users/{doomed.id}").status_code == 404
    assert doomed.get(f"/api/files/{record['id']}").status_code == 401
    assert client.post(
        "/api/auth/login", json={"username": "doomed", "password": doomed.password}
    ).status_code == 401


# ---------------------------------------------------------------------------
# Managing plans
# ---------------------------------------------------------------------------


def test_create_edit_and_delete_a_plan(admin):
    created = admin.post("/api/admin/plans", json={
        "name": "Student Pack",
        "description": "For a semester.",
        "storage_mb": 500 * 1024,
        "price_monthly": 99,
        "price_yearly": 990,
        "features": "500 GB of storage\nEmail support",
        "sort_order": 9,
    })
    assert created.status_code == 201, created.text
    plan = created.json()

    assert plan["code"] == "student-pack"      # slugged from the name
    assert plan["feature_list"] == ["500 GB of storage", "Email support"]
    assert plan["subscriber_count"] == 0

    updated = admin.put(f"/api/admin/plans/{plan['id']}", json={"price_monthly": 79}).json()
    assert updated["price_monthly"] == 79

    assert admin.delete(f"/api/admin/plans/{plan['id']}").status_code == 200
    assert admin.put(f"/api/admin/plans/{plan['id']}", json={"name": "Ghost"}).status_code == 404


def test_duplicate_plan_codes_conflict(admin):
    first = admin.post("/api/admin/plans", json={"name": "Twin Plan", "storage_mb": 1024}).json()
    again = admin.post("/api/admin/plans", json={"name": "Twin Plan", "storage_mb": 1024})

    assert again.status_code == 409
    admin.delete(f"/api/admin/plans/{first['id']}")


def test_changing_a_plans_allowance_moves_every_subscriber(admin, henry):
    plan = admin.post("/api/admin/plans", json={
        "name": "Elastic", "storage_mb": 50 * 1024, "price_monthly": 10, "price_yearly": 100
    }).json()

    admin.post(
        f"/api/admin/users/{henry.id}/subscription",
        json={"plan_id": plan["id"], "billing_cycle": "monthly"},
    )
    assert henry.get("/api/plans/me").json()["storage_limit"] == 50 * 1024

    admin.put(f"/api/admin/plans/{plan['id']}", json={"storage_mb": 80 * 1024})

    # The subscriber's limit followed the plan without them doing anything.
    assert henry.get("/api/plans/me").json()["storage_limit"] == 80 * 1024
    assert henry.get("/api/storage").json()["total_storage"] == 80 * 1024


def test_a_plan_with_subscribers_cannot_be_deleted(admin, henry):
    plans = admin.get("/api/admin/plans").json()
    elastic = next(plan for plan in plans if plan["code"] == "elastic")
    assert elastic["subscriber_count"] == 1

    res = admin.delete(f"/api/admin/plans/{elastic['id']}")
    assert res.status_code == 409
    assert "Move them first" in res.json()["message"]

    # Retiring it is the supported way to withdraw it.
    assert admin.put(
        f"/api/admin/plans/{elastic['id']}", json={"is_active": False}
    ).json()["is_active"] is False

    # A retired plan disappears from the user's catalogue but they keep it.
    assert not any(p["code"] == "elastic" for p in henry.get("/api/plans").json())
    assert henry.get("/api/plans/me").json()["plan"]["code"] == "elastic"

    # And it can no longer be handed to anybody else.
    assert admin.post(
        f"/api/admin/users/{henry.id}/subscription",
        json={"plan_id": elastic["id"], "billing_cycle": "monthly"},
    ).status_code == 400

    admin.delete(f"/api/admin/users/{henry.id}/subscription")


def test_the_free_default_is_protected(admin):
    plans = admin.get("/api/admin/plans").json()
    free = next(plan for plan in plans if plan["is_free"])

    assert admin.delete(f"/api/admin/plans/{free['id']}").status_code == 400
    assert admin.put(f"/api/admin/plans/{free['id']}", json={"is_active": False}).status_code == 400
    assert admin.put(f"/api/admin/plans/{free['id']}", json={"is_free": False}).status_code == 400


def test_marking_a_new_plan_free_moves_the_flag(admin, client):
    from tests.conftest import Actor

    plans = admin.get("/api/admin/plans").json()
    previous = next(plan for plan in plans if plan["is_free"])

    replacement = admin.post("/api/admin/plans", json={
        "name": "Starter", "storage_mb": 10 * 1024, "is_free": True
    }).json()
    assert replacement["is_free"] is True

    after = admin.get("/api/admin/plans").json()
    assert len([plan for plan in after if plan["is_free"]]) == 1
    assert next(p for p in after if p["id"] == previous["id"])["is_free"] is False

    # New accounts land on whichever plan holds the flag now.
    newcomer = Actor(client, "starterkid")
    assert newcomer.get("/api/plans/me").json()["plan"]["code"] == "starter"
    assert newcomer.get("/api/storage").json()["total_storage"] == 10 * 1024

    # Put the original back so the rest of the suite sees the usual catalogue.
    # The newcomer has to come off the temporary plan first, or deleting it is
    # refused - and asserting the delete keeps this cleanup from leaking.
    admin.put(f"/api/admin/plans/{previous['id']}", json={"is_free": True})
    admin.delete(f"/api/admin/users/{newcomer.id}/subscription")
    assert admin.delete(f"/api/admin/plans/{replacement['id']}").status_code == 200
