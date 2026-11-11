from datetime import datetime, timedelta


def test_share_with_a_registered_user_shows_up_in_their_received_list(alice, bob):
    record = alice.upload("shared-report.pdf", b"report bytes").json()["uploaded"][0]

    res = alice.post("/api/shares", json={"file_id": record["id"], "shared_to_username": "bob"})
    assert res.status_code == 201, res.text

    received = bob.get("/api/shares/received").json()
    entry = next(s for s in received if s["file_id"] == record["id"])
    assert entry["file_name"] == "shared-report.pdf"
    assert entry["shared_by_name"] == "Alice Tester"

    # The recipient can now read and download it.
    assert bob.get(f"/api/files/{record['id']}").status_code == 200
    assert bob.get(f"/api/files/{record['id']}/download").content == b"report bytes"


def test_shared_with_me_search_filters_by_name_and_owner(alice, bob):
    record = alice.upload("physics-notes.txt", b"notes").json()["uploaded"][0]
    alice.post("/api/shares", json={"file_id": record["id"], "shared_to_username": "bob"})

    assert any(s["file_name"] == "physics-notes.txt" for s in bob.get("/api/shares/received?q=physics").json())
    assert any(s["file_name"] == "physics-notes.txt" for s in bob.get("/api/shares/received?q=alice").json())
    assert bob.get("/api/shares/received?q=zzzznomatch").json() == []


def test_cannot_share_a_file_you_do_not_own(alice, bob):
    record = alice.upload("not-yours.txt", b"x").json()["uploaded"][0]
    res = bob.post("/api/shares", json={"file_id": record["id"], "shared_to_username": "alice"})
    assert res.status_code == 403


def test_public_link_token_is_long_and_random(alice, client):
    record = alice.upload("public.txt", b"public bytes").json()["uploaded"][0]
    share = alice.post("/api/shares", json={"file_id": record["id"]}).json()

    assert len(share["share_link"]) == 48
    assert share["share_link"].isalnum()
    assert not share["share_link"].isdigit()  # never a guessable id

    info = client.get(f"/api/share/{share['share_link']}")
    assert info.status_code == 200
    assert info.json()["file_name"] == "public.txt"
    assert info.json()["requires_password"] is False

    dl = client.get(f"/api/share/{share['share_link']}/download")
    assert dl.status_code == 200
    assert dl.content == b"public bytes"


def test_unknown_or_guessed_share_token_is_404(client):
    assert client.get("/api/share/1").status_code == 404
    assert client.get("/api/share/deadbeef").status_code == 404


def test_password_protected_link_requires_the_password(alice, client):
    record = alice.upload("protected.txt", b"protected bytes").json()["uploaded"][0]
    share = alice.post(
        "/api/shares", json={"file_id": record["id"], "password": "letmein"}
    ).json()
    token = share["share_link"]

    assert client.get(f"/api/share/{token}").json()["requires_password"] is True

    assert client.get(f"/api/share/{token}/download").status_code == 401
    assert client.get(f"/api/share/{token}/download?password=wrong").status_code == 401
    assert client.post(f"/api/share/{token}/verify", json={"password": "wrong"}).status_code == 401

    assert client.post(f"/api/share/{token}/verify", json={"password": "letmein"}).status_code == 200
    ok = client.get(f"/api/share/{token}/download?password=letmein")
    assert ok.status_code == 200
    assert ok.content == b"protected bytes"


def test_share_password_is_hashed_not_stored_in_plaintext(alice):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import FileShare

    record = alice.upload("hashcheck.txt", b"x").json()["uploaded"][0]
    share = alice.post("/api/shares", json={"file_id": record["id"], "password": "sup3rsecret"}).json()

    db = SessionLocal()
    try:
        row = db.execute(select(FileShare).where(FileShare.id == share["id"])).scalar_one()
        assert row.password != "sup3rsecret"
        assert row.password.startswith("$2")
    finally:
        db.close()


def test_expired_link_is_rejected(alice, client):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import FileShare

    record = alice.upload("expiring.txt", b"gone soon").json()["uploaded"][0]
    share = alice.post(
        "/api/shares",
        json={"file_id": record["id"], "expiry_date": (datetime.utcnow() + timedelta(days=1)).isoformat()},
    ).json()
    token = share["share_link"]

    assert client.get(f"/api/share/{token}").status_code == 200

    db = SessionLocal()
    try:
        row = db.execute(select(FileShare).where(FileShare.id == share["id"])).scalar_one()
        row.expiry_date = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    assert client.get(f"/api/share/{token}").status_code == 410
    assert client.get(f"/api/share/{token}/download").status_code == 410


def test_expiry_date_in_the_past_is_refused(alice):
    record = alice.upload("past-expiry.txt", b"x").json()["uploaded"][0]
    res = alice.post(
        "/api/shares",
        json={"file_id": record["id"], "expiry_date": (datetime.utcnow() - timedelta(days=1)).isoformat()},
    )
    assert res.status_code == 400


def test_revoking_a_share_removes_the_recipients_access(alice, bob):
    record = alice.upload("revoke-me.txt", b"bytes").json()["uploaded"][0]
    share = alice.post("/api/shares", json={"file_id": record["id"], "shared_to_username": "bob"}).json()

    assert bob.get(f"/api/files/{record['id']}").status_code == 200
    assert bob.delete(f"/api/shares/{share['id']}").status_code == 403  # not the owner
    assert alice.delete(f"/api/shares/{share['id']}").status_code == 200
    assert bob.get(f"/api/files/{record['id']}").status_code == 403


def test_trashed_file_is_not_reachable_through_its_share_link(alice, bob, client):
    record = alice.upload("will-be-trashed.txt", b"bytes").json()["uploaded"][0]
    share = alice.post("/api/shares", json={"file_id": record["id"]}).json()
    alice.post("/api/shares", json={"file_id": record["id"], "shared_to_username": "bob"})

    alice.delete(f"/api/files/{record['id']}")

    assert client.get(f"/api/share/{share['share_link']}").status_code == 404
    assert record["id"] not in [s["file_id"] for s in bob.get("/api/shares/received").json()]


def test_shared_word_document_includes_file_kind(alice, bob):
    # Create a Word document
    doc_res = alice.post("/api/files", json={"name": "Shared Notes", "type": "word"})
    assert doc_res.status_code == 201
    doc = doc_res.json()

    # Share it with Bob
    share_res = alice.post("/api/shares", json={"file_id": doc["id"], "shared_to_username": "bob"})
    assert share_res.status_code == 201

    # Check Bob's received shares
    received = bob.get("/api/shares/received").json()
    shared_doc = next((s for s in received if s["file_id"] == doc["id"]), None)
    assert shared_doc is not None
    assert shared_doc["file_kind"] == "word"
    assert shared_doc["file_name"].endswith(".docx")


def test_viewer_cannot_edit_shared_document(alice, bob):
    # Alice creates a Word document
    doc_res = alice.post("/api/files", json={"name": "Report", "type": "word"})
    assert doc_res.status_code == 201
    doc = doc_res.json()

    # Alice saves some content
    alice.put(f"/api/files/{doc['id']}", json={"document_content": "<p>Original content</p>"})

    # Alice shares it with Bob as VIEWER (read-only)
    alice.post("/api/shares", json={"file_id": doc["id"], "shared_to_username": "bob", "permission": "viewer"})

    # Bob can read it
    bob_view = bob.get(f"/api/files/{doc['id']}")
    assert bob_view.status_code == 200
    assert bob_view.json()["document_content"] == "<p>Original content</p>"

    # But Bob cannot edit it
    edit_attempt = bob.put(f"/api/files/{doc['id']}", json={"document_content": "<p>Modified by Bob</p>"})
    assert edit_attempt.status_code == 403, edit_attempt.text

    # Content should still be original
    alice_check = alice.get(f"/api/files/{doc['id']}")
    assert alice_check.json()["document_content"] == "<p>Original content</p>"


def test_editor_can_edit_shared_document(alice, bob):
    # Alice creates a Word document
    doc_res = alice.post("/api/files", json={"name": "Shared Doc", "type": "word"})
    assert doc_res.status_code == 201
    doc = doc_res.json()

    # Alice saves some content
    alice.put(f"/api/files/{doc['id']}", json={"document_content": "<p>Alice's content</p>"})

    # Alice shares it with Bob as EDITOR
    alice.post("/api/shares", json={"file_id": doc["id"], "shared_to_username": "bob", "permission": "editor"})

    # Bob can read it
    bob_view = bob.get(f"/api/files/{doc['id']}")
    assert bob_view.status_code == 200
    assert bob_view.json()["document_content"] == "<p>Alice's content</p>"

    # Bob CAN edit it
    edit_result = bob.put(f"/api/files/{doc['id']}", json={"document_content": "<p>Bob's edit</p>"})
    assert edit_result.status_code == 200, edit_result.text
    assert edit_result.json()["document_content"] == "<p>Bob's edit</p>"

    # Alice sees Bob's changes
    alice_check = alice.get(f"/api/files/{doc['id']}")
    assert alice_check.json()["document_content"] == "<p>Bob's edit</p>"

