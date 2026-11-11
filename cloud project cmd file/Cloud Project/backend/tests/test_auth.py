def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_register_hashes_password_and_never_returns_it(client, alice):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.username == "alice")).scalar_one()
        assert user.password != alice.password
        assert user.password.startswith("$2")  # bcrypt
    finally:
        db.close()

    body = alice.get("/api/auth/me").json()
    assert "password" not in body
    assert body["username"] == "alice"


def test_registering_never_grants_admin(alice, bob):
    """Not even to the first account. The administrator comes from configuration,
    so signing up first must not be a way in."""
    assert alice.get("/api/auth/me").json()["role"] == "user"
    assert bob.get("/api/auth/me").json()["role"] == "user"


def test_the_configured_administrator_exists_and_can_sign_in(admin):
    body = admin.get("/api/auth/me").json()
    assert body["role"] == "admin"
    assert body["status"] == "active"


def test_new_accounts_start_on_the_free_plan(alice):
    body = alice.get("/api/plans/me").json()
    assert body["plan"]["is_free"] is True
    assert body["plan"]["storage_mb"] == 25 * 1024      # 25 GB
    assert body["subscription"]["billing_cycle"] == "free"
    assert body["subscription"]["ends_at"] is None      # free never lapses
    assert body["storage_limit"] == 25 * 1024


def test_duplicate_username_and_email_conflict(client, alice):
    dup_user = client.post(
        "/api/auth/register",
        json={"fullname": "Copy Cat", "username": "alice", "email": "other@example.com", "password": "Passw0rd!23"},
    )
    assert dup_user.status_code == 409

    dup_mail = client.post(
        "/api/auth/register",
        json={"fullname": "Copy Cat", "username": "notalice", "email": "alice@example.com", "password": "Passw0rd!23"},
    )
    assert dup_mail.status_code == 409


def test_login_with_username_and_with_email(client, alice):
    for identifier in ("alice", "alice@example.com"):
        res = client.post("/api/auth/login", json={"username": identifier, "password": alice.password})
        assert res.status_code == 200, res.text
        assert res.json()["user"]["username"] == "alice"


def test_login_with_wrong_password_is_rejected(client, alice):
    res = client.post("/api/auth/login", json={"username": "alice", "password": "wrong-password"})
    assert res.status_code == 401
    assert res.json()["success"] is False


def test_protected_route_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_disabled_user_cannot_log_in_or_use_token(client):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import User

    reg = client.post(
        "/api/auth/register",
        json={"fullname": "Dis Abled", "username": "disabled", "email": "disabled@example.com", "password": "Passw0rd!23"},
    )
    token = reg.json()["access_token"]

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.username == "disabled")).scalar_one()
        user.status = "disabled"
        db.commit()
    finally:
        db.close()

    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    login = client.post("/api/auth/login", json={"username": "disabled", "password": "Passw0rd!23"})
    assert login.status_code == 403


def test_logout_is_logged(alice):
    assert alice.post("/api/auth/logout").status_code == 200
    activities = [a["activity"] for a in alice.get("/api/activity").json()]
    assert "LOGOUT" in activities
    assert "LOGIN" in activities
