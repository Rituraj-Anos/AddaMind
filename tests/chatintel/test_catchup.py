import io

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.chatintel import catchup, db, ingest, memory

NIGHT = """10/03/25, 9:00 pm - Priya Sen: Saturday Goa plan final?
10/03/25, 9:05 pm - Suman Ghosh: haan main hoon
10/03/25, 11:00 pm - Priya Sen: @Suman Ghosh tickets tu book karega?
10/03/25, 11:01 pm - Rohan Das: ek minute
10/03/25, 11:02 pm - Kabir Malhotra: Suman bhai kal 10 baje station?
10/03/25, 11:03 pm - Priya Sen: Final: Saturday 10 am Howrah
"""
MORNING = NIGHT + """11/03/25, 8:00 am - Rohan Das: good morning
11/03/25, 8:02 am - Priya Sen: Suman??
"""


def upload(pid, text, name="WhatsApp Chat with College Friends.txt"):
    job = ingest.create_job(pid, name)
    ingest.save_upload(io.BytesIO(text.encode()), pid, job)
    ingest.run_job(pid, job)


@pytest.fixture()
def chat():
    pid = db.create_project("Suman")["id"]
    upload(pid, NIGHT)
    cid = db.list_chats(pid)[0]["id"]
    me = next(p["id"] for p in db.list_participants(pid) if p["name"] == "Suman Ghosh")
    db.update_participant(pid, me, is_me=True)
    return pid, cid


def ids_by_text(pid, cid):
    return {m["text"]: m["id"] for m in db.messages_window(pid, cid, limit=50)}


def test_unread_starts_after_your_last_message(chat):
    pid, cid = chat
    s = catchup.summary(pid, cid)
    assert s["mode"] == "auto" and s["label"] == "after your last message"
    assert s["unread"] == 4 and s["people"] == 3
    assert s["senders"][0] == {"participant_id": s["senders"][0]["participant_id"], "name": "Priya Sen", "messages": 2}
    t = ids_by_text(pid, cid)
    assert set(s["mentions"]) == {t["@Suman Ghosh tickets tu book karega?"], t["Suman bhai kal 10 baje station?"]}


def test_other_starting_points(chat):
    pid, cid = chat
    assert catchup.summary(pid, cid, "day")["unread"] == 5  # everyone but Suman in the last 24 hours
    assert catchup.summary(pid, cid, "time", "2025-03-10 23:01")["unread"] == 3
    with pytest.raises(ValueError):
        catchup.summary(pid, cid, "upload")  # uploaded once, so nothing is "new since the last upload"
    with pytest.raises(ValueError):
        catchup.summary(pid, cid, "time", "yesterday")
    upload(pid, MORNING)
    s = catchup.summary(pid, cid, "upload")
    assert s["unread"] == 2 and s["options"]["upload"] is True
    assert catchup.summary(pid, cid)["unread"] == 6  # still after Suman's 9:05 pm message


def test_read_marks_are_per_browser(chat):
    pid, cid = chat
    last = catchup.summary(pid, cid)["last_message_id"]
    assert catchup.mark_read(pid, cid, last, "a" * 32)
    assert catchup.summary(pid, cid, owner="a" * 32)["unread"] == 0
    assert catchup.summary(pid, cid, owner="a" * 32)["label"] == "after you marked it caught up"
    assert catchup.summary(pid, cid, owner="b" * 32)["unread"] == 4
    assert not catchup.mark_read(pid, cid, 999999, "a" * 32)


def test_without_a_me_it_falls_back_to_the_last_day():
    pid = db.create_project("P")["id"]
    upload(pid, NIGHT)
    cid = db.list_chats(pid)[0]["id"]
    for p in db.list_participants(pid):
        db.update_participant(pid, p["id"], is_me=False)
    s = catchup.summary(pid, cid)
    assert s["mode"] == "day" and s["me"] is None and s["unread"] == 6


def test_the_read_keeps_only_real_ids_and_every_mention(chat, monkeypatch):
    pid, cid = chat
    t = ids_by_text(pid, cid)
    ask, own, plan = t["@Suman Ghosh tickets tu book karega?"], t["haan main hoon"], t["Final: Saturday 10 am Howrah"]
    fake = catchup.CatchupRead(
        tldr="Plan is final [[m:%d]]." % plan,
        topics=[catchup.Topic(title="Goa plan", summary="Priya fixed the plan.", message_ids=[plan, 424242]),
                catchup.Topic(title="Made up", summary="x", message_ids=[424242])],
        needs_you=[catchup.NeedsYou(message_id=ask, why="asks you to book tickets",
                                    replies=["haan kar dunga [m:1]", "kal subah", "tickets tu book karega?"]),
                   catchup.NeedsYou(message_id=own, why="your own message", replies=["x"]),
                   catchup.NeedsYou(message_id=424242, why="invented", replies=["x"])],
        decisions=[catchup.Decision(text="Saturday 10 am at Howrah", message_ids=[plan])])
    prompts = []
    monkeypatch.setattr(memory, "cached_structured", lambda parts, prompt, schema: prompts.append(prompt) or fake)
    r = catchup.read(pid, cid)
    assert "Suman Ghosh" in prompts[0] and "haan main hoon" in prompts[0]  # the user's style comes along
    assert r["tldr"] == "Plan is final."
    assert [x["title"] for x in r["topics"]] == ["Goa plan"] and r["topics"][0]["message_ids"] == [plan]
    needs = {n["message"]["id"]: n for n in r["needs_you"]}
    assert set(needs) == {ask, t["Suman bhai kal 10 baje station?"]}  # own and invented dropped, the mention added
    assert needs[ask]["replies"] == ["haan kar dunga", "kal subah"] and needs[ask]["source"] == "read"
    assert needs[t["Suman bhai kal 10 baje station?"]]["source"] == "mention"
    assert r["decisions"] == [{"text": "Saturday 10 am at Howrah", "message_ids": [plan]}]


def test_nothing_unread_needs_no_model(chat, monkeypatch):
    pid, cid = chat
    catchup.mark_read(pid, cid, catchup.summary(pid, cid)["last_message_id"], None)
    monkeypatch.setattr(memory, "cached_structured", lambda *a: pytest.fail("no model call when caught up"))
    r = catchup.read(pid, cid)
    assert r["unread"] == 0 and r["needs_you"] == []


def test_api_routes_and_public_demo(chat, monkeypatch):
    pid, cid = chat
    c, a = TestClient(app), {"X-Visitor": "a" * 32}
    assert c.get(f"/projects/{pid}/chats/{cid}/catchup", headers=a).json()["unread"] == 4
    assert c.get(f"/projects/{pid}/chats/{cid}/catchup?mode=time&from_ts=2025-03-10T23:01", headers=a).json()["unread"] == 3
    assert c.get(f"/projects/{pid}/chats/{cid}/catchup?mode=upload", headers=a).status_code == 400
    assert c.get(f"/projects/{pid}/chats/{cid}/catchup?mode=time&from_ts=bad", headers=a).status_code == 422
    monkeypatch.setenv("ADDAMIND_PUBLIC", "1")  # the demo is read-only, but your own read mark is allowed
    last = c.get(f"/projects/{pid}/chats/{cid}/catchup", headers=a).json()["last_message_id"]
    r = c.post(f"/projects/{pid}/chats/{cid}/catchup/mark", json={"message_id": last}, headers=a)
    assert r.status_code == 200 and r.json()["unread"] == 0
    assert c.get(f"/projects/{pid}/chats/{cid}/catchup", headers={"X-Visitor": "b" * 32}).json()["unread"] == 4
