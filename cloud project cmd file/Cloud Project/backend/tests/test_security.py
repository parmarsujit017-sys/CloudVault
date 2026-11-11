"""Explicit attempts to reach another user's data by changing IDs in the URL."""

import pytest


@pytest.fixture(scope="module")
def victim_data(alice):
    folder = alice.post("/api/folders", json={"folder_name": "Victim Vault"}).json()
    record = alice.upload("victim.txt", b"confidential", folder_id=folder["id"]).json()["uploaded"][0]
    return {"folder_id": folder["id"], "file_id": record["id"]}


@pytest.mark.parametrize(
    "method,template,body",
    [
        ("get", "/api/folders/{folder_id}", None),
        ("put", "/api/folders/{folder_id}", {"folder_name": "hijacked"}),
        ("delete", "/api/folders/{folder_id}", None),
        ("get", "/api/files/{file_id}", None),
        ("get", "/api/files/{file_id}/download", None),
        ("delete", "/api/files/{file_id}", None),
        ("put", "/api/files/{file_id}/rename", {"original_name": "hijacked.txt"}),
        ("put", "/api/files/{file_id}/move", {"folder_id": None}),
        ("put", "/api/files/{file_id}/star", {"is_starred": True}),
        ("delete", "/api/trash/{file_id}", None),
        ("post", "/api/trash/{file_id}/restore", None),
    ],
)
def test_id_tampering_is_rejected_with_403(bob, victim_data, method, template, body):
    """Every one of these sends a fully valid request - only the ID is someone
    else's - so a 403 proves the ownership check itself is doing the work."""
    url = template.format(**victim_data)
    call = getattr(bob, method)
    res = call(url, json=body) if body is not None else call(url)
    assert res.status_code == 403, f"{method.upper()} {url} returned {res.status_code}"


def test_every_protected_endpoint_rejects_an_anonymous_caller(client, victim_data):
    for url in (
        "/api/auth/me",
        "/api/users/me",
        "/api/folders",
        "/api/files",
        "/api/trash",
        "/api/shares/received",
        "/api/shares/sent",
        "/api/storage",
        "/api/activity",
        "/api/settings",
        "/api/dashboard",
        "/api/search?q=a",
        f"/api/files/{victim_data['file_id']}/download",
    ):
        assert client.get(url).status_code == 401, url


def test_upload_dir_is_not_reachable_over_http(client, victim_data):
    for url in (
        "/uploads/users/1/files/anything.txt",
        "/backend/.env",
        "/backend/cloud_storage.db",
        "/../backend/.env",
        "/%2e%2e/backend/.env",
    ):
        assert client.get(url).status_code in (404, 400), url


def test_a_forged_token_is_rejected(client):
    from jose import jwt

    forged = jwt.encode({"sub": "1"}, "not-the-real-secret", algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_an_expired_token_is_rejected(client, alice):
    from datetime import datetime, timedelta

    from jose import jwt

    from app.config import settings

    expired = jwt.encode(
        {"sub": str(alice.id), "exp": datetime.utcnow() - timedelta(minutes=5)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_a_traversal_filename_cannot_escape_the_upload_root(alice):
    from sqlalchemy import select

    from app.config import settings
    from app.database import SessionLocal
    from app.models import File

    res = alice.upload("../../../../evil.txt", b"nope")
    assert res.status_code == 201
    record = res.json()["uploaded"][0]
    assert record["original_name"] == "evil.txt"

    db = SessionLocal()
    try:
        path = db.execute(select(File.file_path).where(File.id == record["id"])).scalar_one()
    finally:
        db.close()

    resolved = (settings.upload_path / path).resolve()
    assert settings.upload_path in resolved.parents


def test_the_client_cannot_choose_its_own_user_id(client, alice, bob):
    """user_id is always taken from the token, never from the request body."""
    res = bob.post("/api/folders", json={"folder_name": "Spoofed", "user_id": alice.id})
    assert res.status_code == 201
    assert res.json()["user_id"] == bob.id


def test_a_share_cannot_be_created_on_behalf_of_someone_else(alice, bob):
    record = alice.upload("spoof-share.txt", b"x").json()["uploaded"][0]
    res = bob.post(
        "/api/shares",
        json={"file_id": record["id"], "shared_by": alice.id, "shared_to_username": "bob"},
    )
    assert res.status_code in (403, 422)
