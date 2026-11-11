import pytest


def test_single_upload_stores_uuid_name_and_keeps_original(alice):
    res = alice.upload("college notes.pdf", b"PDF-CONTENT" * 10)
    assert res.status_code == 201, res.text
    record = res.json()["uploaded"][0]

    assert record["original_name"] == "college notes.pdf"
    assert record["file_name"] != record["original_name"]
    assert len(record["file_name"].split(".")[0]) == 32  # uuid4 hex
    assert record["file_size"] == len(b"PDF-CONTENT" * 10)


def test_uploaded_bytes_really_land_on_disk(alice):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import File
    from app.services.storage_backend import storage_backend

    payload = b"real bytes on disk"
    record = alice.upload("ondisk.txt", payload).json()["uploaded"][0]

    db = SessionLocal()
    try:
        row = db.execute(select(File).where(File.id == record["id"])).scalar_one()
        assert storage_backend.exists(row.file_path)
        assert storage_backend.absolute(row.file_path).read_bytes() == payload
    finally:
        db.close()


def test_multiple_upload_in_one_request(alice):
    res = alice.client.post(
        "/api/files/upload",
        headers=alice.headers,
        files=[
            ("files", ("one.txt", b"one", "text/plain")),
            ("files", ("two.txt", b"two", "text/plain")),
            ("files", ("three.txt", b"three", "text/plain")),
        ],
    )
    assert res.status_code == 201
    assert len(res.json()["uploaded"]) == 3


def test_upload_into_a_folder_and_list_it(alice):
    folder = alice.post("/api/folders", json={"folder_name": "Reports"}).json()
    alice.upload("q1.txt", b"q1", folder_id=folder["id"])

    listed = alice.get(f"/api/files?folder_id={folder['id']}").json()
    assert [f["original_name"] for f in listed] == ["q1.txt"]


def test_cannot_upload_into_another_users_folder(alice, bob):
    folder = alice.post("/api/folders", json={"folder_name": "Alice Private"}).json()
    res = bob.upload("intruder.txt", b"x", folder_id=folder["id"])
    assert res.status_code == 403


def test_blocked_executable_extension_is_refused(alice):
    res = alice.upload("virus.exe", b"MZ")
    assert res.status_code == 400
    assert "not allowed" in res.json()["message"]


def test_upload_over_max_file_size_is_refused(alice):
    # MAX_FILE_SIZE_MB is 5 in the test environment.
    res = alice.upload("huge.bin", b"0" * (6 * 1024 * 1024))
    assert res.status_code == 400
    assert "limit" in res.json()["message"].lower()


def test_download_returns_the_bytes_under_the_original_name(alice):
    payload = b"downloadable content"
    record = alice.upload("my report.txt", payload).json()["uploaded"][0]

    res = alice.get(f"/api/files/{record['id']}/download")
    assert res.status_code == 200
    assert res.content == payload
    # Starlette percent-encodes the filename per RFC 5987.
    disposition = res.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert "my%20report.txt" in disposition


def test_download_is_logged(alice):
    record = alice.upload("logged.txt", b"log me").json()["uploaded"][0]
    alice.get(f"/api/files/{record['id']}/download")
    logs = alice.get("/api/activity?activity=DOWNLOAD").json()
    assert any(entry["file_name"] == "logged.txt" for entry in logs)


def test_another_user_cannot_read_or_download_my_file(alice, bob):
    record = alice.upload("secret.txt", b"top secret").json()["uploaded"][0]
    assert bob.get(f"/api/files/{record['id']}").status_code == 403
    assert bob.get(f"/api/files/{record['id']}/download").status_code == 403
    assert bob.delete(f"/api/files/{record['id']}").status_code == 403
    assert bob.put(f"/api/files/{record['id']}/rename", json={"original_name": "x"}).status_code == 403


def test_rename_move_and_star(alice):
    folder = alice.post("/api/folders", json={"folder_name": "Sorted"}).json()
    record = alice.upload("before.txt", b"data").json()["uploaded"][0]

    renamed = alice.put(f"/api/files/{record['id']}/rename", json={"original_name": "after.txt"})
    assert renamed.json()["original_name"] == "after.txt"

    moved = alice.put(f"/api/files/{record['id']}/move", json={"folder_id": folder["id"]})
    assert moved.json()["folder_id"] == folder["id"]

    starred = alice.put(f"/api/files/{record['id']}/star", json={"is_starred": True})
    assert starred.json()["is_starred"] is True
    assert record["id"] in [f["id"] for f in alice.get("/api/files?starred=true").json()]


def test_cannot_move_a_file_into_another_users_folder(alice, bob):
    folder = bob.post("/api/folders", json={"folder_name": "Bob Only"}).json()
    record = alice.upload("mine.txt", b"mine").json()["uploaded"][0]
    res = alice.put(f"/api/files/{record['id']}/move", json={"folder_id": folder["id"]})
    assert res.status_code == 403


def test_user_can_create_and_save_word_document(alice):
    res = alice.post("/api/files", json={"name": "Project Report", "type": "word"})
    assert res.status_code == 201, res.text
    doc = res.json()
    assert doc["original_name"].endswith(".docx")
    assert doc["type"] == "word"

    updated = alice.put(
        f"/api/files/{doc['id']}",
        json={"name": "Project Report", "document_content": "<p><b>Hello</b> world</p>"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["document_content"] == "<p><b>Hello</b> world</p>"

    reopened = alice.get(f"/api/files/{doc['id']}").json()
    assert reopened["document_content"] == "<p><b>Hello</b> world</p>"


def test_user_cannot_access_another_users_document(alice, bob):
    created = alice.post("/api/files", json={"name": "Secret plan", "type": "word"}).json()
    assert bob.get(f"/api/files/{created['id']}").status_code == 403
    assert bob.put(f"/api/files/{created['id']}", json={"name": "Hacked"}).status_code == 403
    assert bob.get(f"/api/files/{created['id']}/download").status_code == 403


def test_user_can_create_and_save_excel_sheet(alice):
    res = alice.post("/api/files", json={"name": "Sales Report", "type": "excel"})
    assert res.status_code == 201, res.text
    sheet = res.json()
    assert sheet["original_name"].endswith(".xlsx")
    assert sheet["type"] == "excel"

    payload = {
        "name": "Sales Report",
        "spreadsheet_data": {
            "sheets": [
                {"name": "Sheet1", "data": [["Product", "Quantity", "Price"], ["Laptop", 2, 50000]]}
            ]
        },
    }
    updated = alice.put(f"/api/files/{sheet['id']}", json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["spreadsheet_data"]["sheets"][0]["data"][1][0] == "Laptop"


def test_document_created_in_folder_stays_in_folder(alice):
    # Create a folder with a unique name
    import time
    folder_name = f"Reports_{int(time.time() * 1000) % 10000}"
    folder_res = alice.post("/api/folders", json={"folder_name": folder_name})
    assert folder_res.status_code == 201, folder_res.text
    folder = folder_res.json()

    # Create a Word document inside the folder
    doc_res = alice.post("/api/files", json={"name": "Q1 Report", "type": "word", "folder_id": folder["id"]})
    assert doc_res.status_code == 201, doc_res.text
    doc = doc_res.json()
    assert doc["folder_id"] == folder["id"]
    assert doc["original_name"].endswith(".docx")

    # Create an Excel spreadsheet inside the folder
    sheet_res = alice.post("/api/files", json={"name": "Budget", "type": "excel", "folder_id": folder["id"]})
    assert sheet_res.status_code == 201, sheet_res.text
    sheet = sheet_res.json()
    assert sheet["folder_id"] == folder["id"]
    assert sheet["original_name"].endswith(".xlsx")

    # List files in the folder - should see both
    list_res = alice.get(f"/api/files?folder_id={folder['id']}")
    assert list_res.status_code == 200
    files = list_res.json()
    assert len(files) == 2
    assert doc["id"] in [f["id"] for f in files]
    assert sheet["id"] in [f["id"] for f in files]


def test_saved_document_remains_in_file_list(alice):
    # Create a Word document
    doc_res = alice.post("/api/files", json={"name": "Minutes", "type": "word"})
    assert doc_res.status_code == 201, doc_res.text
    doc = doc_res.json()
    doc_id = doc["id"]

    # Save content to it
    save_res = alice.put(
        f"/api/files/{doc_id}",
        json={"document_content": "<p>Meeting notes</p>"}
    )
    assert save_res.status_code == 200, save_res.text
    saved = save_res.json()
    assert saved["document_content"] == "<p>Meeting notes</p>"
    assert saved["file_size"] > 0, "File size should be updated after save"

    # List root files - the saved document should appear
    list_res = alice.get("/api/files?root_only=true")
    assert list_res.status_code == 200
    files = list_res.json()
    assert any(f["id"] == doc_id for f in files), "Saved document should appear in file list"

    # Verify it's retrievable
    get_res = alice.get(f"/api/files/{doc_id}")
    assert get_res.status_code == 200
    retrieved = get_res.json()
    assert retrieved["document_content"] == "<p>Meeting notes</p>"

