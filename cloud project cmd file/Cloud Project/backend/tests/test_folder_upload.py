"""Uploading a whole folder: the directory tree has to survive the trip."""

import io
import zipfile

import pytest


@pytest.fixture(scope="module")
def carol(client):
    from tests.conftest import Actor

    return Actor(client, "carol")


def test_tree_creates_every_level_and_returns_the_id_map(carol):
    res = carol.post(
        "/api/folders/tree",
        json={
            "parent_folder": None,
            "paths": [
                "Project",
                "Project/src",
                "Project/src/components",
                "Project/docs",
            ],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()

    assert body["created"] == 4
    assert set(body["folders"]) == {
        "Project",
        "Project/src",
        "Project/src/components",
        "Project/docs",
    }

    # The map really does describe a nested tree, not four root folders.
    project = carol.get(f"/api/folders/{body['folders']['Project']}").json()
    assert sorted(f["folder_name"] for f in project["folders"]) == ["docs", "src"]

    deep = carol.get(f"/api/folders/{body['folders']['Project/src/components']}").json()
    assert [c["folder_name"] for c in deep["breadcrumb"]] == ["Project", "src", "components"]


def test_intermediate_folders_are_implied_by_a_leaf_path(carol):
    res = carol.post(
        "/api/folders/tree", json={"paths": ["Media/2024/June/raw"]}
    )
    assert res.status_code == 201
    folders = res.json()["folders"]
    assert set(folders) == {"Media", "Media/2024", "Media/2024/June", "Media/2024/June/raw"}


def test_re_uploading_the_same_folder_merges_instead_of_duplicating(carol):
    first = carol.post("/api/folders/tree", json={"paths": ["Merge/inner"]}).json()
    second = carol.post("/api/folders/tree", json={"paths": ["Merge/inner", "Merge/other"]}).json()

    assert second["created"] == 1  # only "Merge/other" was new
    assert second["folders"]["Merge"] == first["folders"]["Merge"]
    assert second["folders"]["Merge/inner"] == first["folders"]["Merge/inner"]


def test_traversal_segments_cannot_escape_the_users_tree(carol):
    res = carol.post("/api/folders/tree", json={"paths": ["../../etc/evil"]})
    assert res.status_code == 201

    folders = res.json()["folders"]
    # ".." segments are dropped, so what is left is an ordinary nested folder.
    assert set(folders) == {"etc", "etc/evil"}
    assert carol.get(f"/api/folders/{folders['etc']}").json()["folder"]["parent_folder"] is None


def test_files_land_in_the_folder_their_path_names(carol):
    tree = carol.post("/api/folders/tree", json={"paths": ["Site/css"]}).json()["folders"]

    carol.upload("app.css", b"body{}", folder_id=tree["Site/css"])
    carol.upload("index.html", b"<html>", folder_id=tree["Site"])

    css = carol.get(f"/api/folders/{tree['Site/css']}").json()
    site = carol.get(f"/api/folders/{tree['Site']}").json()

    assert [f["original_name"] for f in css["files"]] == ["app.css"]
    assert [f["original_name"] for f in site["files"]] == ["index.html"]


def test_tree_beyond_the_depth_limit_is_refused(carol):
    deep = "/".join(f"L{i}" for i in range(1, 26))
    res = carol.post("/api/folders/tree", json={"paths": [deep]})
    assert res.status_code == 400
    assert "deep" in res.json()["message"].lower()


def test_another_user_cannot_build_a_tree_in_my_folder(carol, bob):
    root = carol.post("/api/folders", json={"folder_name": "CarolPrivate"}).json()
    res = bob.post("/api/folders/tree", json={"parent_folder": root["id"], "paths": ["sneaky"]})
    assert res.status_code == 403


def test_folder_downloads_as_a_zip_that_keeps_the_structure(carol):
    tree = carol.post(
        "/api/folders/tree", json={"paths": ["Zipped/a/b", "Zipped/empty"]}
    ).json()["folders"]

    carol.upload("top.txt", b"top", folder_id=tree["Zipped"])
    carol.upload("deep.txt", b"deep", folder_id=tree["Zipped/a/b"])

    res = carol.get(f"/api/folders/{tree['Zipped']}/download")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"

    archive = zipfile.ZipFile(io.BytesIO(res.content))
    names = set(archive.namelist())

    assert "top.txt" in names
    assert "a/b/deep.txt" in names
    assert "empty/" in names          # empty folders are preserved too
    assert archive.read("a/b/deep.txt") == b"deep"


def test_resolved_echoes_back_the_exact_paths_that_were_sent(carol):
    """The uploader looks its own raw `webkitRelativePath` dirs up in here, so
    server-side name cleaning must not break the lookup."""
    res = carol.post(
        "/api/folders/tree", json={"paths": ["Odd Name#1/sub dir", "Odd Name#1"]}
    )
    assert res.status_code == 201
    body = res.json()

    assert set(body["resolved"]) == {"Odd Name#1/sub dir", "Odd Name#1"}

    # The names really were cleaned, yet the raw keys still resolve.
    made = carol.get(f"/api/folders/{body['resolved']['Odd Name#1']}").json()
    assert made["folder"]["folder_name"] == "Odd Name_1"
    assert body["resolved"]["Odd Name#1/sub dir"] == body["folders"]["Odd Name_1/sub dir"]
