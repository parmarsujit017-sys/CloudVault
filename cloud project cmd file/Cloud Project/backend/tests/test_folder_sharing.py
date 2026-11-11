"""Sharing a whole folder: direct shares, public links and the browse endpoints."""

import io
import zipfile
from datetime import datetime, timedelta

import pytest


@pytest.fixture(scope="module")
def erin(client):
    from tests.conftest import Actor

    return Actor(client, "erin")


@pytest.fixture(scope="module")
def frank(client):
    from tests.conftest import Actor

    return Actor(client, "frank")


@pytest.fixture(scope="module")
def album(erin):
    """Album > 2024 > Trip, with a file at each level."""
    folders = erin.post(
        "/api/folders/tree", json={"paths": ["Album/2024/Trip", "Album/blank"]}
    ).json()["folders"]

    erin.upload("cover.txt", b"cover", folder_id=folders["Album"])
    erin.upload("summary.txt", b"summary", folder_id=folders["Album/2024"])
    erin.upload("beach.txt", b"beach", folder_id=folders["Album/2024/Trip"])
    return folders


# ---------------------------------------------------------------------------
# Direct shares
# ---------------------------------------------------------------------------


def test_folder_share_appears_in_the_recipients_received_list(erin, frank, album):
    res = erin.post(
        "/api/shares/folder", json={"folder_id": album["Album"], "shared_to_username": "frank"}
    )
    assert res.status_code == 201, res.text
    share = res.json()

    assert share["kind"] == "folder"
    assert share["folder_name"] == "Album"
    assert share["item_count"] == 3  # every file in the subtree

    received = frank.get("/api/shares/received").json()
    entry = next(s for s in received if s["kind"] == "folder" and s["folder_id"] == album["Album"])
    assert entry["shared_by_name"] == "Erin Tester"


def test_recipient_of_a_folder_share_can_read_files_nested_inside_it(erin, frank, album):
    deep = erin.get(f"/api/folders/{album['Album/2024/Trip']}").json()["files"][0]

    # Access is granted by the folder share, not by any per-file share.
    assert frank.get(f"/api/files/{deep['id']}").status_code == 200
    assert frank.get(f"/api/files/{deep['id']}/download").content == b"beach"


def test_a_stranger_still_cannot_read_files_in_the_shared_folder(erin, bob, album):
    deep = erin.get(f"/api/folders/{album['Album/2024/Trip']}").json()["files"][0]
    assert bob.get(f"/api/files/{deep['id']}").status_code == 403


def test_sharing_the_same_folder_with_the_same_person_twice_conflicts(erin, album):
    res = erin.post(
        "/api/shares/folder", json={"folder_id": album["Album"], "shared_to_username": "frank"}
    )
    assert res.status_code == 409


def test_cannot_share_a_folder_you_do_not_own(bob, album):
    res = bob.post(
        "/api/shares/folder", json={"folder_id": album["Album"], "shared_to_username": "erin"}
    )
    assert res.status_code == 403


def test_revoking_a_folder_share_removes_the_access_it_granted(erin, frank, album):
    folder = erin.post("/api/folders", json={"folder_name": "Temporary"}).json()
    record = erin.upload("temp.txt", b"temp", folder_id=folder["id"]).json()["uploaded"][0]

    share = erin.post(
        "/api/shares/folder", json={"folder_id": folder["id"], "shared_to_username": "frank"}
    ).json()
    assert frank.get(f"/api/files/{record['id']}").status_code == 200

    assert erin.delete(f"/api/shares/folder/{share['id']}").status_code == 200
    assert frank.get(f"/api/files/{record['id']}").status_code == 403


def test_only_the_creator_can_revoke_a_folder_share(erin, frank, album):
    folder = erin.post("/api/folders", json={"folder_name": "NotYours"}).json()
    share = erin.post(
        "/api/shares/folder", json={"folder_id": folder["id"], "shared_to_username": "frank"}
    ).json()
    assert frank.delete(f"/api/shares/folder/{share['id']}").status_code == 403


# ---------------------------------------------------------------------------
# Public links
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def public_token(erin, album):
    return erin.post("/api/shares/folder", json={"folder_id": album["Album"]}).json()["share_link"]


def test_public_info_describes_a_folder_link(client, public_token):
    body = client.get(f"/api/share/{public_token}").json()
    assert body["kind"] == "folder"
    assert body["file_name"] == "Album"
    assert body["item_count"] == 3
    assert body["folder_count"] == 3  # 2024, Trip, blank
    assert body["requires_password"] is False


def test_public_listing_walks_the_folder_one_level_at_a_time(client, public_token):
    root = client.get(f"/api/share/{public_token}/list").json()
    assert root["folder_name"] == "Album"
    assert sorted(e["name"] for e in root["entries"] if e["kind"] == "folder") == ["2024", "blank"]
    assert [e["name"] for e in root["entries"] if e["kind"] == "file"] == ["cover.txt"]

    deep = client.get(f"/api/share/{public_token}/list?path=2024/Trip").json()
    assert deep["folder_name"] == "Trip"
    assert deep["breadcrumb"] == ["2024", "Trip"]
    assert [e["name"] for e in deep["entries"]] == ["beach.txt"]


def test_public_link_downloads_a_file_from_inside_the_folder(client, public_token):
    listing = client.get(f"/api/share/{public_token}/list?path=2024/Trip").json()
    file_id = listing["entries"][0]["file_id"]

    res = client.get(f"/api/share/{public_token}/download?file_id={file_id}")
    assert res.status_code == 200
    assert res.content == b"beach"


def test_public_link_cannot_reach_a_file_outside_the_shared_folder(client, erin, public_token):
    outsider = erin.upload("outside.txt", b"nope").json()["uploaded"][0]
    res = client.get(f"/api/share/{public_token}/download?file_id={outsider['id']}")
    assert res.status_code == 404


def test_public_link_cannot_escape_the_share_with_a_traversal_path(client, public_token):
    assert client.get(f"/api/share/{public_token}/list?path=../..").status_code == 200
    # ".." collapses to the share root rather than the owner's parent folder.
    assert client.get(f"/api/share/{public_token}/list?path=../..").json()["folder_name"] == "Album"
    assert client.get(f"/api/share/{public_token}/list?path=nosuchfolder").status_code == 404


def test_public_link_downloads_the_whole_folder_as_a_zip(client, public_token):
    res = client.get(f"/api/share/{public_token}/download-all")
    assert res.status_code == 200

    archive = zipfile.ZipFile(io.BytesIO(res.content))
    names = set(archive.namelist())
    assert {"cover.txt", "2024/summary.txt", "2024/Trip/beach.txt"} <= names
    assert archive.read("2024/Trip/beach.txt") == b"beach"


def test_password_protected_folder_link_gates_listing_and_download(erin, client, album):
    token = erin.post(
        "/api/shares/folder", json={"folder_id": album["Album"], "password": "opensesame"}
    ).json()["share_link"]

    assert client.get(f"/api/share/{token}").json()["requires_password"] is True
    assert client.get(f"/api/share/{token}/list").status_code == 401
    assert client.get(f"/api/share/{token}/download-all").status_code == 401

    assert client.post(f"/api/share/{token}/verify", json={"password": "wrong"}).status_code == 401
    assert client.post(f"/api/share/{token}/verify", json={"password": "opensesame"}).status_code == 200
    assert client.get(f"/api/share/{token}/list?password=opensesame").status_code == 200


def test_expired_folder_link_is_gone(erin, client, album, monkeypatch):
    future = datetime.utcnow() + timedelta(minutes=5)
    token = erin.post(
        "/api/shares/folder",
        json={"folder_id": album["Album"], "expiry_date": future.isoformat()},
    ).json()["share_link"]

    assert client.get(f"/api/share/{token}").status_code == 200

    # Rewind the expiry past "now" the same way the file-share tests do.
    from app.database import SessionLocal
    from app.models import FolderShare

    db = SessionLocal()
    try:
        share = db.query(FolderShare).filter(FolderShare.share_link == token).one()
        share.expiry_date = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    assert client.get(f"/api/share/{token}").status_code == 410
    assert client.get(f"/api/share/{token}/list").status_code == 410


def test_expiry_must_be_in_the_future(erin, album):
    past = (datetime.utcnow() - timedelta(days=1)).isoformat()
    res = erin.post(
        "/api/shares/folder", json={"folder_id": album["Album"], "expiry_date": past}
    )
    assert res.status_code == 400


def test_sent_list_holds_both_kinds_of_share(erin, album):
    record = erin.upload("sent-file.txt", b"x").json()["uploaded"][0]
    erin.post("/api/shares", json={"file_id": record["id"]})

    sent = erin.get("/api/shares/sent").json()
    kinds = {s["kind"] for s in sent}
    assert kinds == {"file", "folder"}
    # Newest first, and every entry carries a usable public URL.
    assert all(s["share_url"] for s in sent)


def test_deleting_a_shared_folder_removes_its_shares(erin, frank):
    folder = erin.post("/api/folders", json={"folder_name": "Doomed"}).json()
    erin.post("/api/shares/folder", json={"folder_id": folder["id"], "shared_to_username": "frank"})

    assert erin.delete(f"/api/folders/{folder['id']}").status_code == 200
    assert not [
        s for s in frank.get("/api/shares/received").json()
        if s["kind"] == "folder" and s["folder_id"] == folder["id"]
    ]


def test_the_shared_with_me_counter_includes_shared_folders(erin, frank):
    """The sidebar badge reads this number, so it has to match what the
    Shared-with-me page lists - which now includes folders."""
    before = frank.get("/api/dashboard").json()["shared_files"]
    listed_before = len(frank.get("/api/shares/received").json())
    assert before == listed_before

    folder = erin.post("/api/folders", json={"folder_name": "CounterCheck"}).json()
    erin.post("/api/shares/folder", json={"folder_id": folder["id"], "shared_to_username": "frank"})

    after = frank.get("/api/dashboard").json()["shared_files"]
    assert after == before + 1
    assert after == len(frank.get("/api/shares/received").json())
