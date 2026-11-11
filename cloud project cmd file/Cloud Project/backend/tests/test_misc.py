def test_settings_persist_in_the_database(alice):
    defaults = alice.get("/api/settings").json()
    assert defaults["theme"] == "light"
    assert defaults["notifications"] is True
    assert defaults["language"] == "English"

    alice.put("/api/settings", json={"theme": "dark", "notifications": False, "language": "Hindi"})

    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import Setting

    db = SessionLocal()
    try:
        row = db.execute(select(Setting).where(Setting.user_id == alice.id)).scalar_one()
        assert (row.theme, row.notifications, row.language) == ("dark", False, "Hindi")
    finally:
        db.close()

    # Restore so later assertions are not surprised.
    alice.put("/api/settings", json={"theme": "light", "notifications": True, "language": "English"})


def test_invalid_theme_is_a_validation_error(alice):
    res = alice.put("/api/settings", json={"theme": "neon"})
    assert res.status_code == 422
    assert res.json()["success"] is False


def test_settings_are_per_user(alice, bob):
    alice.put("/api/settings", json={"theme": "dark"})
    assert bob.get("/api/settings").json()["theme"] == "light"
    alice.put("/api/settings", json={"theme": "light"})


def test_profile_update_and_conflict_handling(alice, bob):
    res = alice.put("/api/users/me", json={"fullname": "Alice Updated"})
    assert res.json()["fullname"] == "Alice Updated"

    conflict = alice.put("/api/users/me", json={"username": "bob"})
    assert conflict.status_code == 409

    conflict_mail = alice.put("/api/users/me", json={"email": "bob@example.com"})
    assert conflict_mail.status_code == 409

    alice.put("/api/users/me", json={"fullname": "Alice Tester"})


def test_password_change_requires_the_current_password(client, alice):
    wrong = alice.put(
        "/api/users/me/password", json={"current_password": "nope", "new_password": "Newpass!234"}
    )
    assert wrong.status_code == 400

    ok = alice.put(
        "/api/users/me/password",
        json={"current_password": alice.password, "new_password": "Newpass!234"},
    )
    assert ok.status_code == 200
    assert client.post("/api/auth/login", json={"username": "alice", "password": "Newpass!234"}).status_code == 200

    alice.put("/api/users/me/password", json={"current_password": "Newpass!234", "new_password": alice.password})


def test_avatar_upload_rejects_non_images_and_accepts_a_png(alice):
    bad = alice.post(
        "/api/users/me/avatar", files={"file": ("script.js", b"alert(1)", "text/javascript")}
    )
    assert bad.status_code == 400

    png = bytes.fromhex("89504e470d0a1a0a") + b"fake png body"
    good = alice.post("/api/users/me/avatar", files={"file": ("me.png", png, "image/png")})
    assert good.status_code == 200
    assert good.json()["profile_image"].endswith(".png")
    assert alice.get("/api/users/me/avatar").status_code == 200


def test_dashboard_uses_live_counts(alice):
    body = alice.get("/api/dashboard").json()
    files = alice.get("/api/files?root_only=false").json()

    assert body["total_files"] >= len(files)
    assert body["total_folders"] == len(alice.get("/api/folders?all=true").json())
    assert body["trash_files"] == len(alice.get("/api/trash").json())
    assert round(body["storage_used"] + body["available_storage"], 2) == round(body["storage_limit"], 2)
    assert isinstance(body["recent_files"], list)
    assert isinstance(body["recent_activity"], list)


def test_search_matches_partial_names_and_stays_scoped_to_the_user(alice, bob):
    alice.post("/api/folders", json={"folder_name": "Searchable Folder"})
    alice.upload("searchable-file.txt", b"data")

    body = alice.get("/api/search?q=searchab").json()
    assert any(f["original_name"] == "searchable-file.txt" for f in body["files"])
    assert any(f["folder_name"] == "Searchable Folder" for f in body["folders"])

    other = bob.get("/api/search?q=searchab").json()
    assert other["files"] == [] and other["folders"] == []


def test_search_with_sql_metacharacters_is_safe(alice):
    res = alice.get("/api/search?q=' OR 1=1 --")
    assert res.status_code == 200
    assert res.json()["files"] == []
    # The users table is still intact afterwards.
    assert alice.get("/api/auth/me").status_code == 200


def test_activity_log_records_every_action_type(client):
    """Drive one user through every logged action, then assert the log."""
    from tests.conftest import Actor

    actor = Actor(client, "logger")

    client.post("/api/auth/login", json={"username": "logger", "password": actor.password})

    folder = actor.post("/api/folders", json={"folder_name": "Logged Folder"}).json()
    actor.put(f"/api/folders/{folder['id']}", json={"folder_name": "Logged Folder 2"})

    record = actor.upload("logged-everything.txt", b"payload").json()["uploaded"][0]
    actor.get(f"/api/files/{record['id']}/download")

    share = actor.post("/api/shares", json={"file_id": record["id"]}).json()
    actor.delete(f"/api/shares/{share['id']}")

    actor.put("/api/users/me", json={"fullname": "Logger Renamed"})
    actor.put("/api/settings", json={"theme": "dark"})

    actor.delete(f"/api/files/{record['id']}")
    actor.post(f"/api/trash/{record['id']}/restore")
    actor.delete(f"/api/files/{record['id']}")
    actor.delete(f"/api/trash/{record['id']}")

    actor.delete(f"/api/folders/{folder['id']}")
    actor.post("/api/auth/logout")

    activities = {entry["activity"] for entry in actor.get("/api/activity?limit=200").json()}
    for expected in {
        "LOGIN", "LOGOUT", "UPLOAD", "DOWNLOAD", "CREATE_FOLDER", "RENAME_FOLDER",
        "DELETE_FOLDER", "DELETE_FILE", "RESTORE_FILE", "PERMANENT_DELETE",
        "SHARE_FILE", "UNSHARE_FILE", "UPDATE_PROFILE", "UPDATE_SETTINGS",
    }:
        assert expected in activities, f"{expected} was never logged"


def test_activity_is_private_and_admin_only_for_the_system_view(alice, bob, admin):
    assert all(entry["user_id"] == bob.id for entry in bob.get("/api/activity").json())
    assert bob.get("/api/activity/all").status_code == 403    # bob is not an admin
    assert alice.get("/api/activity/all").status_code == 403  # nor is alice
    assert admin.get("/api/activity/all").status_code == 200


def test_activity_records_an_ip_address(alice):
    entries = alice.get("/api/activity").json()
    assert any(entry["ip_address"] for entry in entries)


def test_user_search_never_leaks_emails_or_hashes(alice):
    results = alice.get("/api/users/search?q=bob").json()
    assert results and results[0]["username"] == "bob"
    assert "email" not in results[0]
    assert "password" not in results[0]


def test_errors_are_structured_json_not_tracebacks(client, alice):
    res = alice.get("/api/files/999999")
    assert res.status_code == 404
    assert res.json() == {"success": False, "message": "File not found"}

    bad = client.post("/api/auth/register", json={"username": "x"})
    assert bad.status_code == 422
    assert bad.json()["success"] is False
    assert "Traceback" not in bad.text
