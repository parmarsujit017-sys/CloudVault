def used_mb(actor):
    return actor.get("/api/storage").json()["used_storage"]


def test_upload_increases_usage_and_delete_keeps_it_until_purge(alice):
    before = used_mb(alice)
    payload = b"z" * (2 * 1024 * 1024)  # 2 MB
    record = alice.upload("twomb.bin", payload).json()["uploaded"][0]

    after_upload = used_mb(alice)
    assert round(after_upload - before, 1) == 2.0

    # Trashed files still occupy quota, exactly like Google Drive.
    alice.delete(f"/api/files/{record['id']}")
    assert used_mb(alice) == after_upload

    alice.delete(f"/api/trash/{record['id']}")
    assert round(used_mb(alice), 2) == round(before, 2)


def test_storage_total_used_and_available_stay_consistent(alice):
    body = alice.get("/api/storage").json()
    assert round(body["total_storage"] - body["used_storage"], 2) == round(body["available_storage"], 2)
    assert body["total_storage"] == 25 * 1024.0    # the Free plan allowance


def test_delete_restore_and_permanent_delete_cycle(alice):
    record = alice.upload("cycle.txt", b"cycle" * 100).json()["uploaded"][0]
    fid = record["id"]

    assert alice.delete(f"/api/files/{fid}").status_code == 200
    assert fid not in [f["id"] for f in alice.get("/api/files").json()]

    entry = next(t for t in alice.get("/api/trash").json() if t["file_id"] == fid)
    assert entry["auto_delete"] > entry["deleted_at"]

    assert alice.post(f"/api/trash/{fid}/restore").status_code == 200
    assert fid in [f["id"] for f in alice.get("/api/files").json()]
    assert fid not in [t["file_id"] for t in alice.get("/api/trash").json()]

    alice.delete(f"/api/files/{fid}")
    assert alice.delete(f"/api/trash/{fid}").status_code == 200
    assert alice.get(f"/api/files/{fid}").status_code == 404


def test_permanent_delete_removes_the_bytes_from_disk(alice):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import File
    from app.services.storage_backend import storage_backend

    record = alice.upload("erase-me.txt", b"erase").json()["uploaded"][0]

    db = SessionLocal()
    try:
        path = db.execute(select(File.file_path).where(File.id == record["id"])).scalar_one()
    finally:
        db.close()

    assert storage_backend.exists(path)
    alice.delete(f"/api/files/{record['id']}")
    alice.delete(f"/api/trash/{record['id']}")
    assert not storage_backend.exists(path)


def test_another_user_cannot_touch_my_trash(alice, bob):
    record = alice.upload("private-trash.txt", b"x").json()["uploaded"][0]
    alice.delete(f"/api/files/{record['id']}")

    assert record["id"] not in [t["file_id"] for t in bob.get("/api/trash").json()]
    assert bob.post(f"/api/trash/{record['id']}/restore").status_code == 403
    assert bob.delete(f"/api/trash/{record['id']}").status_code == 403


def test_empty_trash_removes_everything_for_that_user_only(alice, bob):
    bob_record = bob.upload("bob-keeps-this.txt", b"bob").json()["uploaded"][0]
    bob.delete(f"/api/files/{bob_record['id']}")

    alice.upload("a.txt", b"a")
    for f in alice.get("/api/files").json():
        alice.delete(f"/api/files/{f['id']}")

    assert alice.delete("/api/trash").status_code == 200
    assert alice.get("/api/trash").json() == []
    assert len(bob.get("/api/trash").json()) == 1


def test_quota_blocks_an_upload_that_would_not_fit(client):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import User
    from tests.conftest import Actor

    tiny = Actor(client, "tinyquota")

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.username == "tinyquota")).scalar_one()
        user.storage_limit = 1.0  # 1 MB
        db.commit()
    finally:
        db.close()

    ok = tiny.upload("fits.bin", b"0" * (400 * 1024))
    assert ok.status_code == 201

    too_big = tiny.upload("does-not-fit.bin", b"0" * (900 * 1024))
    assert too_big.status_code == 400
    assert "Storage limit exceeded" in too_big.json()["message"]
