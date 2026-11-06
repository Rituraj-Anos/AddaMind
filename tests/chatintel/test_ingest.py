import io
import time
import zipfile

import pytest

from backend.chatintel import db, ingest

GROUP = """03/02/25, 7:30 pm - Priya Sen created group "College Friends"
03/02/25, 7:31 pm - Priya Sen: Goa plan final?
03/02/25, 7:32 pm - Rohan Das: PTT-20250203-WA0001.opus (file attached)
03/02/25, 7:33 pm - +91 98311 45678: ok
03/02/25, 7:33 pm - +91 98311 45678: ok
04/02/25, 9:00 am - Kabir Malhotra: @\u2068Priya Sen\u2069 haan
"""
NEWER = GROUP + "05/03/25, 1:10 am - Kabir Malhotra: 3 baje Maggi\n"
DIRECT = """[03/07/25, 9:15:02 PM] Shrimant Roy: bhai 2000 de de
[03/07/25, 9:16:40 PM] Suman Ghosh: done
"""


def make_zip(text: str, media: dict[str, bytes] | None = None, txt_name="WhatsApp Chat with College Friends.txt") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(txt_name, text)
        for name, data in (media or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ADDAMIND_DATA", str(tmp_path))
    return tmp_path


def upload(pid: int, filename: str, data: bytes, chat_id=None) -> dict:
    job_id = ingest.create_job(pid, filename, chat_id)
    ingest.save_upload(io.BytesIO(data), pid, job_id)
    ingest.run_job(pid, job_id)
    return db.get_job(pid, job_id)


def test_upload_creates_chat_participants_and_media(data_dir):
    pid = db.create_project("Suman")["id"]
    job = upload(pid, "WhatsApp Chat with College Friends.zip",
                 make_zip(GROUP, {"PTT-20250203-WA0001.opus": b"OggS-voice"}))
    assert job["status"] == "done", job["error"]
    chat = db.get_chat(pid, job["chat_id"])
    assert (chat["title"], chat["kind"], chat["status"], chat["message_count"]) == ("College Friends", "group", "ready", 6)
    people = {p["name"]: p for p in db.list_participants(pid)}
    assert people["+91 ••••• ••678"]["masked"] and people["+91 ••••• ••678"]["message_count"] == 2
    assert job["info"]["media_saved"] == 1 and chat["media_count"] == 1
    voice = next(m for m in db.messages_window(pid, chat["id"]) if m["kind"] == "voice")
    row, path = db.get_media(pid, voice["media"]["id"])
    assert path.read_bytes() == b"OggS-voice" and row["mime"] == "audio/ogg"
    with db.connect() as con:  # mentions resolved to participant ids
        assert con.execute("SELECT COUNT(*) FROM message_mentions").fetchone()[0] == 1


def test_same_export_twice_adds_nothing_and_newer_export_merges():
    pid = db.create_project("Suman")["id"]
    first = upload(pid, "WhatsApp Chat with College Friends.txt", GROUP.encode())
    again = upload(pid, "WhatsApp Chat with College Friends.txt", GROUP.encode())
    assert again["chat_id"] == first["chat_id"] and again["info"]["inserted"] == 0
    newer = upload(pid, "WhatsApp Chat with College Friends.zip",
                   make_zip(NEWER, {"PTT-20250203-WA0001.opus": b"x"}))
    assert newer["info"]["inserted"] == 1 and newer["info"]["months"] == ["2025-03"]
    assert newer["info"]["media_saved"] == 1  # the zip filled in media the .txt could not carry
    assert len(db.list_chats(pid)) == 1 and db.get_chat(pid, first["chat_id"])["message_count"] == 7


def test_direct_chat_guesses_me_and_shares_participants_across_chats():
    pid = db.create_project("Suman")["id"]
    upload(pid, "WhatsApp Chat with College Friends.txt", (GROUP + "05/02/25, 8:00 pm - Suman Ghosh: hi\n").encode())
    upload(pid, "WhatsApp Chat - Shrimant Roy.zip", make_zip(DIRECT, txt_name="_chat.txt"))
    people = {p["name"]: p for p in db.list_participants(pid)}
    assert people["Suman Ghosh"]["is_me"] and len(people["Suman Ghosh"]["chat_ids"]) == 2
    assert not people["Shrimant Roy"]["is_me"]


def test_reads_across_projects_fail():
    a = db.create_project("A")["id"]
    b = db.create_project("B")["id"]
    job = upload(a, "WhatsApp Chat with College Friends.zip", make_zip(GROUP, {"PTT-20250203-WA0001.opus": b"x"}))
    cid = job["chat_id"]
    mid = db.messages_window(a, cid)[0]["id"]
    media_id = next(m for m in db.messages_window(a, cid) if m["media"])["media"]["id"]
    assert db.get_chat(b, cid) is None and db.messages_window(b, cid) is None
    assert db.get_message(b, mid) is None and db.get_media(b, media_id) is None
    assert db.get_job(b, job["id"]) is None and db.delete_chat(b, cid) is None
    assert db.list_chats(b) == [] and db.list_participants(b) == []
    some = db.list_participants(a)[0]["id"]
    assert not db.update_participant(b, some, is_me=True)
    assert db.get_chat(a, cid) is not None


def test_delete_chat_and_project_remove_rows_and_files(data_dir):
    pid = db.create_project("Suman")["id"]
    job = upload(pid, "WhatsApp Chat with College Friends.zip", make_zip(GROUP, {"PTT-20250203-WA0001.opus": b"x"}))
    cid = job["chat_id"]
    assert db.chat_dir(pid, cid).exists()
    assert db.delete_chat(pid, cid)["files_removed"]
    assert not db.chat_dir(pid, cid).exists()
    with db.connect() as con:
        for table in ("messages", "media", "chat_members", "message_mentions", "messages_fts"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    upload(pid, "WhatsApp Chat - Shrimant Roy.txt", DIRECT.encode())
    assert db.delete_project(pid)["files_removed"]
    assert not db.project_dir(pid).exists()
    with db.connect() as con:
        for table in ("projects", "participants", "chats", "messages", "jobs", "messages_fts"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


@pytest.mark.parametrize("bad", ["../evil.txt", "media/../../evil.jpg", "/abs/evil.jpg", "C:/evil.jpg"])
def test_zip_with_escaping_path_is_rejected(data_dir, bad):
    pid = db.create_project("Suman")["id"]
    job = upload(pid, "WhatsApp Chat with College Friends.zip", make_zip(GROUP, {bad: b"x"}))
    assert job["status"] == "failed" and "outside" in job["error"]
    assert db.list_chats(pid) == []
    assert not any(p.name.startswith("evil") for p in data_dir.rglob("*"))


def test_upload_over_the_size_cap_is_refused(monkeypatch):
    pid = db.create_project("Suman")["id"]
    monkeypatch.setattr(ingest, "MAX_UPLOAD_BYTES", 10)
    job_id = ingest.create_job(pid, "x.txt")
    with pytest.raises(ValueError):
        ingest.save_upload(io.BytesIO(GROUP.encode()), pid, job_id)
    assert not ingest.upload_path(pid, job_id).exists()


def test_merge_participants_moves_messages_and_keeps_alias():
    pid = db.create_project("Suman")["id"]
    upload(pid, "WhatsApp Chat with College Friends.txt", GROUP.encode())
    people = {p["name"]: p["id"] for p in db.list_participants(pid)}
    phone, rohan = people["+91 ••••• ••678"], people["Rohan Das"]
    assert db.merge_participants(pid, phone, rohan)
    after = {p["name"]: p for p in db.list_participants(pid)}
    assert "+91 ••••• ••678" not in after and after["Rohan Das"]["message_count"] == 3
    upload(pid, "WhatsApp Chat with College Friends.txt", NEWER.replace("Kabir Malhotra: 3", "+91 98311 45678: 3").encode())
    assert {p["name"]: p for p in db.list_participants(pid)}["Rohan Das"]["message_count"] == 4


def test_messages_window_and_context():
    pid = db.create_project("Suman")["id"]
    cid = upload(pid, "WhatsApp Chat with College Friends.txt", GROUP.encode())["chat_id"]
    all_ = db.messages_window(pid, cid, limit=200)
    mid = all_[3]["id"]
    ctx = db.get_message(pid, mid, context=2)
    assert [m["id"] for m in ctx["before"]] == [m["id"] for m in all_[1:3]]
    assert [m["id"] for m in ctx["after"]] == [m["id"] for m in all_[4:6]]
    assert [m["id"] for m in db.messages_window(pid, cid, before=mid, limit=2)] == [m["id"] for m in all_[1:3]]


def test_api_end_to_end():
    from fastapi.testclient import TestClient

    from backend.api.main import app

    c = TestClient(app)
    pid = c.post("/projects", json={"name": "Suman"}).json()["id"]
    r = c.post(f"/projects/{pid}/chats", files={"file": ("WhatsApp Chat with College Friends.zip",
                                                         make_zip(GROUP, {"PTT-20250203-WA0001.opus": b"x"}))})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    events = [line for line in c.get(f"/projects/{pid}/jobs/{jid}/events").text.splitlines() if line.startswith("data:")]
    assert '"status": "done"' in events[-1]
    other = c.post("/projects", json={"name": "Other"}).json()["id"]
    cid = c.get(f"/projects/{pid}/jobs/{jid}").json()["chat_id"]
    assert c.get(f"/projects/{other}/chats/{cid}").status_code == 404
    assert c.get(f"/projects/{other}/chats/{cid}/messages").status_code == 404
    assert c.post(f"/projects/{pid}/chats", files={"file": ("notes.pdf", b"x")}).status_code == 400
    assert c.delete(f"/projects/{pid}").status_code == 200
    assert c.get(f"/projects/{pid}").status_code == 404


def test_only_startup_recovery_fails_running_jobs():
    pid = db.create_project("Suman")["id"]
    job_id = ingest.create_job(pid, "x.txt")
    ingest._update(job_id, status="running")
    db._ready.clear()  # a second process opening the database must not touch running jobs
    assert db.get_job(pid, job_id)["status"] == "running"
    assert db.recover_jobs() == 1
    assert db.get_job(pid, job_id)["status"] == "failed"
