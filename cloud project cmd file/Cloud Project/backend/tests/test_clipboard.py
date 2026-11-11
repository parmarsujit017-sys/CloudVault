"""Copy, cut (move) and the batch endpoints behind select-all + paste."""

import pytest


@pytest.fixture(scope="module")
def dave(client):
    from tests.conftest import Actor

    return Actor(client, "dave")


@pytest.fixture(scope="module")
def workspace(dave):
    """Source > inner (with files), plus an empty Target to paste into."""
    folders = dave.post(
        "/api/folders/tree", json={"paths": ["Source/inner", "Target"]}
    ).json()["folders"]

    dave.upload("root-note.txt", b"root note", folder_id=folders["Source"])
    dave.upload("inner-note.txt", b"inner note", folder_id=folders["Source/inner"])
    return folders


# ---------------------------------------------------------------------------
# Copying a single file
# ---------------------------------------------------------------------------


def test_copy_file_into_another_folder(dave, workspace):
    record = dave.upload("copy-me.txt", b"payload").json()["uploaded"][0]

    res = dave.post(f"/api/files/{record['id']}/copy", json={"folder_id": workspace["Target"]})
    assert res.status_code == 201, res.text
    duplicate = res.json()

    assert duplicate["id"] != record["id"]
    assert duplicate["folder_id"] == workspace["Target"]
    assert duplicate["original_name"] == "copy-me.txt"
    # Its own bytes on disk, so it survives the original being trashed.
    assert dave.get(f"/api/files/{duplicate['id']}/download").content == b"payload"

    dave.delete(f"/api/files/{record['id']}")
    assert dave.get(f"/api/files/{duplicate['id']}/download").content == b"payload"


def test_copying_into_the_same_folder_renames_rather_than_clashing(dave):
    record = dave.upload("twin.txt", b"x").json()["uploaded"][0]

    first = dave.post(f"/api/files/{record['id']}/copy", json={"folder_id": None}).json()
    second = dave.post(f"/api/files/{record['id']}/copy", json={"folder_id": None}).json()

    assert first["original_name"] == "twin (copy).txt"
    assert second["original_name"] == "twin (copy 2).txt"


def test_cannot_copy_someone_elses_file(dave, bob):
    record = dave.upload("private.txt", b"secret").json()["uploaded"][0]
    assert bob.post(f"/api/files/{record['id']}/copy", json={"folder_id": None}).status_code == 403


# ---------------------------------------------------------------------------
# Copying a folder
# ---------------------------------------------------------------------------


def test_copy_folder_duplicates_the_whole_subtree(dave, workspace):
    res = dave.post(
        f"/api/folders/{workspace['Source']}/copy", json={"parent_folder": workspace["Target"]}
    )
    assert res.status_code == 201, res.text
    clone = res.json()

    assert clone["id"] != workspace["Source"]
    assert clone["parent_folder"] == workspace["Target"]

    contents = dave.get(f"/api/folders/{clone['id']}").json()
    assert [f["original_name"] for f in contents["files"]] == ["root-note.txt"]
    assert [f["folder_name"] for f in contents["folders"]] == ["inner"]

    inner_id = contents["folders"][0]["id"]
    inner = dave.get(f"/api/folders/{inner_id}").json()
    assert [f["original_name"] for f in inner["files"]] == ["inner-note.txt"]

    # A real copy: the bytes came along, and the original is untouched.
    assert dave.get(f"/api/files/{inner['files'][0]['id']}/download").content == b"inner note"
    assert dave.get(f"/api/folders/{workspace['Source/inner']}").json()["files"]


def test_copying_a_folder_beside_itself_gets_a_copy_suffix(dave, workspace):
    clone = dave.post(
        f"/api/folders/{workspace['Source']}/copy", json={"parent_folder": None}
    ).json()
    assert clone["folder_name"] == "Source (copy)"


def test_a_folder_cannot_be_copied_into_itself(dave, workspace):
    res = dave.post(
        f"/api/folders/{workspace['Source']}/copy",
        json={"parent_folder": workspace["Source/inner"]},
    )
    assert res.status_code == 400
    assert "itself" in res.json()["message"]


# ---------------------------------------------------------------------------
# Batch operations - select all, then cut/copy/paste or delete
# ---------------------------------------------------------------------------


def test_batch_move_relocates_every_selected_file(dave):
    target = dave.post("/api/folders", json={"folder_name": "BatchMove"}).json()
    ids = [
        dave.upload("bm-1.txt", b"1").json()["uploaded"][0]["id"],
        dave.upload("bm-2.txt", b"2").json()["uploaded"][0]["id"],
    ]

    res = dave.post(
        "/api/files/batch", json={"action": "move", "file_ids": ids, "folder_id": target["id"]}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert sorted(body["succeeded"]) == sorted(ids)

    listed = dave.get(f"/api/folders/{target['id']}").json()["files"]
    assert sorted(f["original_name"] for f in listed) == ["bm-1.txt", "bm-2.txt"]


def test_batch_copy_leaves_the_originals_in_place(dave):
    target = dave.post("/api/folders", json={"folder_name": "BatchCopy"}).json()
    record = dave.upload("bc-1.txt", b"1").json()["uploaded"][0]

    res = dave.post(
        "/api/files/batch",
        json={"action": "copy", "file_ids": [record["id"]], "folder_id": target["id"]},
    )
    assert res.status_code == 200
    assert res.json()["succeeded"] == [record["id"]]

    assert dave.get(f"/api/files/{record['id']}").status_code == 200
    assert [f["original_name"] for f in dave.get(f"/api/folders/{target['id']}").json()["files"]] == ["bc-1.txt"]


def test_batch_reports_failures_per_item_and_still_does_the_rest(dave, bob):
    mine = dave.upload("mine.txt", b"1").json()["uploaded"][0]["id"]
    theirs = bob.upload("theirs.txt", b"2").json()["uploaded"][0]["id"]

    res = dave.post("/api/files/batch", json={"action": "trash", "file_ids": [mine, theirs]})
    assert res.status_code == 200
    body = res.json()

    assert body["success"] is False
    assert body["succeeded"] == [mine]
    assert [f["id"] for f in body["failed"]] == [theirs]
    assert "access" in body["failed"][0]["message"].lower()

    # The one that worked really is in the trash.
    assert any(t["file_id"] == mine for t in dave.get("/api/trash").json())


def test_batch_star_and_unstar(dave):
    ids = [dave.upload("star-me.txt", b"1").json()["uploaded"][0]["id"]]

    dave.post("/api/files/batch", json={"action": "star", "file_ids": ids})
    assert dave.get(f"/api/files/{ids[0]}").json()["is_starred"] is True

    dave.post("/api/files/batch", json={"action": "unstar", "file_ids": ids})
    assert dave.get(f"/api/files/{ids[0]}").json()["is_starred"] is False


def test_batch_folder_move_and_delete(dave):
    home = dave.post("/api/folders", json={"folder_name": "BatchHome"}).json()
    one = dave.post("/api/folders", json={"folder_name": "MoveOne"}).json()
    two = dave.post("/api/folders", json={"folder_name": "MoveTwo"}).json()

    res = dave.post(
        "/api/folders/batch",
        json={"action": "move", "folder_ids": [one["id"], two["id"]], "parent_folder": home["id"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["success"] is True
    assert sorted(f["folder_name"] for f in dave.get(f"/api/folders/{home['id']}").json()["folders"]) == [
        "MoveOne",
        "MoveTwo",
    ]

    res = dave.post("/api/folders/batch", json={"action": "delete", "folder_ids": [one["id"]]})
    assert res.status_code == 200
    assert dave.get(f"/api/folders/{one['id']}").status_code == 404


def test_batch_move_refuses_to_put_a_folder_inside_itself(dave):
    parent = dave.post("/api/folders", json={"folder_name": "CycleParent"}).json()
    child = dave.post(
        "/api/folders", json={"folder_name": "CycleChild", "parent_folder": parent["id"]}
    ).json()

    res = dave.post(
        "/api/folders/batch",
        json={"action": "move", "folder_ids": [parent["id"]], "parent_folder": child["id"]},
    )
    assert res.status_code == 200
    assert res.json()["succeeded"] == []
    assert "itself" in res.json()["failed"][0]["message"]


def test_a_moved_item_is_renamed_but_not_called_a_copy(dave):
    """A clash on move means two things wanted the same name - not that anything
    was duplicated, so the suffix must not say "copy"."""
    home = dave.post("/api/folders", json={"folder_name": "ClashHome"}).json()
    away = dave.post("/api/folders", json={"folder_name": "ClashAway"}).json()

    dave.post("/api/folders", json={"folder_name": "Notes", "parent_folder": home["id"]})
    other = dave.post(
        "/api/folders", json={"folder_name": "Notes", "parent_folder": away["id"]}
    ).json()

    res = dave.post(
        "/api/folders/batch",
        json={"action": "move", "folder_ids": [other["id"]], "parent_folder": home["id"]},
    )
    assert res.status_code == 200
    assert res.json()["succeeded"] == [other["id"]]

    names = sorted(f["folder_name"] for f in dave.get(f"/api/folders/{home['id']}").json()["folders"])
    assert names == ["Notes", "Notes (2)"]

    # Files behave the same way, with the suffix kept before the extension.
    first = dave.upload("clash.txt", b"1", folder_id=home["id"]).json()["uploaded"][0]
    second = dave.upload("clash.txt", b"2", folder_id=away["id"]).json()["uploaded"][0]

    dave.post(
        "/api/files/batch",
        json={"action": "move", "file_ids": [second["id"]], "folder_id": home["id"]},
    )
    moved = dave.get(f"/api/files/{second['id']}").json()
    assert moved["original_name"] == "clash (2).txt"
    assert dave.get(f"/api/files/{first['id']}").json()["original_name"] == "clash.txt"


def test_a_copy_still_says_copy(dave):
    home = dave.post("/api/folders", json={"folder_name": "CopyWording"}).json()
    record = dave.upload("doc.pdf", b"1", folder_id=home["id"]).json()["uploaded"][0]

    first = dave.post(f"/api/files/{record['id']}/copy", json={"folder_id": home["id"]}).json()
    second = dave.post(f"/api/files/{record['id']}/copy", json={"folder_id": home["id"]}).json()

    assert first["original_name"] == "doc (copy).pdf"
    assert second["original_name"] == "doc (copy 2).pdf"
