"""Visitor isolation: one browser can't see or change another's projects, and the shared demo is read-only in public."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.chatintel import db

A = {"X-Visitor": "a" * 32}
B = {"X-Visitor": "b" * 32}


@pytest.fixture
def c():
    return TestClient(app)


def test_projects_are_private_to_their_visitor(c):
    pid = c.post("/projects", json={"name": "Mine"}, headers=A).json()["id"]
    shared = db.create_project("Demo")["id"]

    assert {p["id"] for p in c.get("/projects", headers=A).json()} == {pid, shared}
    assert {p["id"] for p in c.get("/projects", headers=B).json()} == {shared}
    assert {p["id"] for p in c.get("/projects").json()} == {shared}

    for path in (f"/projects/{pid}", f"/projects/{pid}/stats", f"/projects/{pid}/participants", f"/projects/{pid}/threads"):
        assert c.get(path, headers=B).status_code == 404, path
        assert c.get(path).status_code == 404, path
        assert c.get(path, headers=A).status_code == 200, path
    assert c.get(f"/projects/{pid}?v={'a' * 32}").status_code == 200  # query form, for <img src>
    assert c.delete(f"/projects/{pid}", headers=B).status_code == 404
    assert c.patch(f"/projects/{pid}", json={"name": "x"}, headers=B).status_code == 404
    assert c.delete(f"/projects/{pid}", headers=A).status_code == 200


def test_bad_visitor_id_is_rejected(c):
    assert c.get("/projects", headers={"X-Visitor": "short"}).status_code == 400
    assert c.get("/projects", headers={"X-Visitor": "x" * 20 + "'; drop"}).status_code == 400


def test_threads_are_private_on_a_shared_project(c):
    pid = db.create_project("Demo")["id"]
    mine = db.create_thread(pid, "recall", "project", None, "my question", A["X-Visitor"])
    db.append_thread(pid, mine, [{"role": "user", "content": "hi"}])
    assert [t["id"] for t in c.get(f"/projects/{pid}/threads", headers=A).json()] == [mine]
    assert c.get(f"/projects/{pid}/threads", headers=B).json() == []
    assert c.get(f"/projects/{pid}/threads/{mine}", headers=B).status_code == 404
    assert c.delete(f"/projects/{pid}/threads/{mine}", headers=B).status_code == 404
    assert c.delete(f"/projects/{pid}/threads/{mine}", headers=A).status_code == 200


def test_public_server_keeps_the_demo_read_only(c, monkeypatch):
    monkeypatch.setenv("ADDAMIND_PUBLIC", "1")
    shared = db.create_project("Demo")["id"]
    assert c.delete(f"/projects/{shared}", headers=A).status_code == 403
    assert c.patch(f"/projects/{shared}", json={"name": "x"}, headers=A).status_code == 403
    assert c.post(f"/projects/{shared}/chats", files={"file": ("a.txt", b"x")}, headers=A).status_code == 403
    assert c.get(f"/projects/{shared}", headers=A).status_code == 200
    assert c.post("/projects", json={"name": "Mine"}).status_code == 400  # must say who it belongs to
    own = c.post("/projects", json={"name": "Mine"}, headers=A).json()["id"]
    assert c.patch(f"/projects/{own}", json={"name": "Renamed"}, headers=A).status_code == 200
    assert c.get("/health").json()["public"] is True


def test_expired_visitor_projects_are_deleted_and_shared_ones_kept():
    old = db.create_project("Old", "a" * 32)["id"]
    new = db.create_project("New", "a" * 32)["id"]
    shared = db.create_project("Demo")["id"]
    db.project_dir(old).mkdir(parents=True)
    past = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(timespec="seconds")
    with db.connect() as con:
        con.execute("UPDATE projects SET created_at = ? WHERE id IN (?, ?)", (past, old, shared))
    assert db.delete_expired(24) == [old]
    assert db.get_project(old) is None and not db.project_dir(old).exists()
    assert db.get_project(new) and db.get_project(shared)
