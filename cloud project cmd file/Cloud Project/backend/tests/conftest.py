"""Test fixtures: every test run gets a throwaway database and upload dir."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="Cloud-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TMP / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(TMP / "uploads")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["SERVE_FRONTEND"] = "false"
os.environ["MAX_FILE_SIZE_MB"] = "5"
os.environ["DEFAULT_STORAGE_LIMIT_MB"] = "15360"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    shutil.rmtree(TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


class Actor:
    """A registered user plus a convenience wrapper for authenticated calls."""

    def __init__(self, client, username: str, register: bool = True, password: str | None = None):
        self.client = client
        self.username = username
        self.password = password or "Passw0rd!23"

        if register:
            res = client.post(
                "/api/auth/register",
                json={
                    "fullname": f"{username.title()} Tester",
                    "username": username,
                    "email": f"{username}@example.com",
                    "password": self.password,
                },
            )
            assert res.status_code == 201, res.text
        else:
            res = client.post(
                "/api/auth/login", json={"username": username, "password": self.password}
            )
            assert res.status_code == 200, res.text

        body = res.json()
        self.token = body["access_token"]
        self.id = body["user"]["id"]
        self.role = body["user"]["role"]

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, url, **kw):
        return self.client.get(url, headers=self.headers, **kw)

    def post(self, url, **kw):
        return self.client.post(url, headers=self.headers, **kw)

    def put(self, url, **kw):
        return self.client.put(url, headers=self.headers, **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self.headers, **kw)

    def upload(self, name: str, content: bytes = b"hello world", folder_id=None):
        url = "/api/files/upload"
        if folder_id is not None:
            url += f"?folder_id={folder_id}"
        return self.post(url, files=[("files", (name, content, "text/plain"))])


@pytest.fixture(scope="session")
def alice(client):
    return Actor(client, "alice")


@pytest.fixture(scope="session")
def bob(client):
    return Actor(client, "bob")


@pytest.fixture(scope="session")
def admin(client):
    """The bootstrap administrator, created from configuration at startup.

    Registration no longer grants admin to anybody, so this is the only way to
    reach the admin-only endpoints.
    """
    from app.config import settings

    actor = Actor(
        client, settings.ADMIN_USERNAME, register=False, password=settings.ADMIN_PASSWORD
    )
    assert actor.role == "admin"
    return actor
