import pytest


@pytest.fixture(scope="module")
def tree(alice):
    """My Files > Documents > College, plus Images."""
    root = alice.post("/api/folders", json={"folder_name": "My Files"}).json()
    docs = alice.post("/api/folders", json={"folder_name": "Documents", "parent_folder": root["id"]}).json()
    college = alice.post("/api/folders", json={"folder_name": "College", "parent_folder": docs["id"]}).json()
    images = alice.post("/api/folders", json={"folder_name": "Images", "parent_folder": root["id"]}).json()
    return {"root": root, "docs": docs, "college": college, "images": images}


def test_create_and_nest_folders(tree):
    assert tree["root"]["parent_folder"] is None
    assert tree["docs"]["parent_folder"] == tree["root"]["id"]
    assert tree["college"]["parent_folder"] == tree["docs"]["id"]


def test_open_folder_returns_children_and_breadcrumb(alice, tree):
    res = alice.get(f"/api/folders/{tree['docs']['id']}")
    assert res.status_code == 200
    body = res.json()
    assert [c["folder_name"] for c in body["breadcrumb"]] == ["My Files", "Documents"]
    assert [f["folder_name"] for f in body["folders"]] == ["College"]


def test_duplicate_name_in_same_parent_conflicts(alice, tree):
    res = alice.post("/api/folders", json={"folder_name": "Documents", "parent_folder": tree["root"]["id"]})
    assert res.status_code == 409


def test_rename_folder(alice, tree):
    fid = tree["images"]["id"]
    res = alice.put(f"/api/folders/{fid}", json={"folder_name": "Pictures"})
    assert res.status_code == 200
    assert res.json()["folder_name"] == "Pictures"


def test_folder_cannot_be_moved_inside_itself(alice, tree):
    res = alice.put(
        f"/api/folders/{tree['root']['id']}", json={"parent_folder": tree["college"]["id"]}
    )
    assert res.status_code == 400


def test_another_user_cannot_read_or_change_my_folder(bob, tree):
    fid = tree["docs"]["id"]
    assert bob.get(f"/api/folders/{fid}").status_code == 403
    assert bob.put(f"/api/folders/{fid}", json={"folder_name": "hijacked"}).status_code == 403
    assert bob.delete(f"/api/folders/{fid}").status_code == 403
    assert bob.post("/api/folders", json={"folder_name": "x", "parent_folder": fid}).status_code == 403


def test_unknown_folder_is_404(alice):
    assert alice.get("/api/folders/999999").status_code == 404


def test_path_traversal_in_folder_name_is_neutralised(alice):
    res = alice.post("/api/folders", json={"folder_name": "../../etc/passwd"})
    assert res.status_code == 201
    assert res.json()["folder_name"] == "passwd"


def test_delete_folder_moves_its_files_to_trash(alice):
    folder = alice.post("/api/folders", json={"folder_name": "Temporary"}).json()
    uploaded = alice.upload("inside.txt", b"x" * 100, folder_id=folder["id"]).json()["uploaded"][0]

    assert alice.delete(f"/api/folders/{folder['id']}").status_code == 200
    assert alice.get(f"/api/folders/{folder['id']}").status_code == 404

    trashed = [t["file_id"] for t in alice.get("/api/trash").json()]
    assert uploaded["id"] in trashed
