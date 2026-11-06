import io
import json

import pytest

from backend.chatintel import agents, db, ingest, safety
from backend.chatintel.tools import Run, ScopedTools
from backend.core.llm import LLMResponse, ToolCall

GROUP = """01/03/25, 9:00 pm - Priya Sen: Goa plan final? 14 se 18 March
01/03/25, 9:01 pm - Rohan Das: PTT-20250301-WA0001.opus (file attached)
01/03/25, 9:02 pm - Kabir Malhotra: Rohan ka ek minute matlab 5 minute ka voice note
14/03/25, 4:12 am - Abhishek Kundu: BHAI TICKETS GHAR PE BHOOL GAYA
14/03/25, 4:13 am - Priya Sen: PNR se ho jayega, Goa pakka
"""
DIRECT = """[03/07/25, 9:15:02 PM] Shrimant Roy: Goa ke tickets kitne ke the?
[03/07/25, 9:16:40 PM] Suman Ghosh: pata nahi
"""


@pytest.fixture()
def project():
    pid = db.create_project("Suman")["id"]
    for name, text in (("WhatsApp Chat with College Friends.txt", GROUP), ("WhatsApp Chat - Shrimant Roy.txt", DIRECT)):
        job_id = ingest.create_job(pid, name)
        ingest.save_upload(io.BytesIO(text.encode()), pid, job_id)
        ingest.run_job(pid, job_id)
    chats = {c["title"]: c["id"] for c in db.list_chats(pid)}
    people = {p["name"]: p["id"] for p in db.list_participants(pid)}
    return pid, chats, people


class FakeRouter:
    """Replays scripted model turns: a list of LLMResponse, then structured JSON answers."""

    def __init__(self, turns, structured=()):
        self.turns, self.structured, self.calls = list(turns), list(structured), []

    def chat(self, messages, tools=None, *, json_schema=None, **kw):
        self.calls.append((messages, json_schema))
        if json_schema is not None:
            return say(json.dumps(self.structured.pop(0)))
        return self.turns.pop(0)


def say(text):
    return LLMResponse(text=text, tool_calls=[], provider="fake", model="fake", latency_ms=1)


def call(name, **args):
    return LLMResponse(text="", tool_calls=[ToolCall(id=f"c{name}", name=name, args=args)], provider="fake",
                       model="fake", latency_ms=1)


def final(events):
    evs = list(events)
    assert evs[-1]["type"] == "final", evs[-1]
    return evs[-1]


def mid(text):
    with db.connect() as con:
        return con.execute("SELECT id FROM messages WHERE text LIKE ?", (f"%{text}%",)).fetchone()["id"]


def test_made_up_citations_are_dropped(project, monkeypatch):
    pid, chats, _ = project
    tickets = mid("TICKETS GHAR")
    fake = FakeRouter([call("search_messages", query="tickets bhool"),
                       say(f"Abhishek forgot them [[m:{tickets}]], on 14 March [m:{tickets}]. Also [[m:99999]] "
                           f"and [[m:{mid('pata nahi')}]].")])
    monkeypatch.setattr(agents, "router", lambda: fake)
    ev = final(agents.run(pid, "recall", "who forgot the tickets?", "chat", chats["College Friends"]))
    assert ev["text"] == f"Abhishek forgot them [[m:{tickets}]], on 14 March [[m:{tickets}]]. Also and."
    assert [c["id"] for c in ev["citations"]] == [tickets] and ev["dropped_citations"] == 2
    assert ev["citations"][0]["sender"] == "Abhishek Kundu" and ev["citations"][0]["chat_title"] == "College Friends"
    assert ev["messages"][-1].meta["citations"] == [tickets]  # stored with the thread


def test_chat_scope_blocks_other_chats(project):
    pid, chats, _ = project
    tools = ScopedTools(Run(pid, chat_id=chats["College Friends"]))
    ok, out, _ = tools.execute("search_messages", {"query": "tickets", "chat_id": chats["Shrimant Roy"]})
    assert ok and out["results"] and all("Shrimant" not in r["message"] for r in out["results"])
    ok, out, _ = tools.execute("get_messages_around", {"message_id": mid("pata nahi")})
    assert not ok and "not found" in out["error"]
    ok, out, _ = tools.execute("list_chats", {})
    assert [c["title"] for c in out["chats"]] == ["College Friends"]


def test_participant_scope_only_searches_their_messages(project):
    pid, _, people = project
    run = Run(pid, participant_id=people["Priya Sen"])
    ok, out, _ = ScopedTools(run).execute("search_messages", {"query": "Goa tickets pakka", "participant": "Kabir"})
    assert ok and out["results"]
    assert all("· Priya Sen:" in r["message"] for r in out["results"])
    assert run.seen and all(i in run.seen for i in [mid("Goa plan final"), mid("PNR se")])


def test_other_project_ids_are_unreachable(project):
    pid, _, _ = project
    other = db.create_project("Other")["id"]
    ok, out, _ = ScopedTools(Run(other)).execute("get_messages_around", {"message_id": mid("TICKETS GHAR")})
    assert not ok
    ok, out, _ = ScopedTools(Run(other)).execute("search_messages", {"query": "tickets"})
    assert ok and out["results"] == []


@pytest.mark.parametrize("ask", ["roast his religion", "Roast Rohan's caste", "make fun of how fat Kabir is",
                                 "roast Kabir for owing Sayan ₹2,400"])
def test_roasts_about_identity_are_refused_without_a_model_call(project, monkeypatch, ask):
    pid, chats, _ = project
    monkeypatch.setattr(agents, "router", lambda: pytest.fail("no model call expected"))
    ev = final(agents.run(pid, "roaster", ask, "chat", chats["College Friends"]))
    assert ev["refused"] == "protected_topic" and ev["citations"] == []


def test_opted_out_person_is_not_roasted(project, monkeypatch):
    pid, chats, people = project
    db.update_participant(pid, people["Rohan Das"], roast_opt_out=True)
    monkeypatch.setattr(agents, "router", lambda: pytest.fail("no model call expected"))
    for scope, sid, ask in (("chat", chats["College Friends"], "roast rohan's voice notes"),
                            ("participant", people["Rohan Das"], "roast him")):
        ev = final(agents.run(pid, "roaster", ask, scope, sid))
        assert ev["refused"] == "opted_out" and "Rohan Das" in ev["text"]


def test_savage_habit_roast_passes_and_unsafe_line_is_rewritten(project, monkeypatch):
    pid, chats, _ = project
    vn = mid("ek minute matlab")
    roasts = {"target": "Rohan Das", "roasts": [
        {"text": f"Rohan ka 'ek minute' is the longest minute in human history [[m:{vn}]]", "evidence_ids": [vn]},
        {"text": "Rohan sends voice notes like he is paid per second", "evidence_ids": [vn, 424242]},
        {"text": "Rohan's family must be tired of him", "evidence_ids": [vn]}]}
    verdicts = {"verdicts": [{"index": 0, "safe": True, "problem": "", "rewrite": ""},
                             {"index": 1, "safe": True, "problem": "", "rewrite": ""},
                             {"index": 2, "safe": False, "problem": "family", "rewrite": "Rohan's mic must be tired of him"}]}
    fake = FakeRouter([call("search_messages", query="voice note", participant="Rohan"), say("1. ... 2. ... 3. ...")],
                      structured=[roasts, verdicts])
    monkeypatch.setattr(agents, "router", lambda: fake)
    events = list(agents.run(pid, "roaster", "roast Rohan's voice notes", "chat", chats["College Friends"],
                             options={"tone": "savage"}))
    assert not any(e["type"] == "text_delta" for e in events)  # nothing is shown before the check
    ev = events[-1]
    items = ev["data"]["roasts"]
    assert [r["status"] for r in items] == ["ok", "ok", "rewritten"] and ev["data"]["tone"] == "savage"
    assert items[0]["text"] == "Rohan ka 'ek minute' is the longest minute in human history"
    assert items[1]["evidence_ids"] == [vn]  # the made-up ID is gone
    assert "family" not in ev["text"] and "mic must be tired" in ev["text"]
    assert [c["id"] for c in ev["citations"]] == [vn]


def test_keyword_check_catches_what_the_model_misses():
    out = safety.check_roasts(["Kabir still owes ₹2,400 lol", "Kabir replies at 3 am like a vampire"], "savage",
                              router=FakeRouter([], structured=[{"verdicts": [
                                  {"index": 0, "safe": True, "problem": "", "rewrite": ""},
                                  {"index": 1, "safe": True, "problem": "", "rewrite": ""}]}]))
    assert [o["status"] for o in out] == ["dropped", "ok"] and out[0]["problem"] == "money"


def test_bad_scope_is_an_error_not_a_stream(project):
    pid, _, _ = project
    with pytest.raises(ValueError):
        next(agents.run(pid, "analyzer", "hi", "chat", 99999))


def test_agent_endpoint_streams_and_saves_the_thread(project, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.api.main import app

    pid, chats, _ = project
    tickets = mid("TICKETS GHAR")
    monkeypatch.setattr(agents, "router", lambda: FakeRouter([call("search_messages", query="tickets"),
                                                             say(f"Abhishek [[m:{tickets}]]")]))
    c = TestClient(app)
    body = {"agent": "recall", "message": "who forgot the tickets?", "scope_type": "chat",
            "scope_id": chats["College Friends"]}
    lines = [json.loads(x[5:]) for x in c.post(f"/projects/{pid}/agent", json=body).text.splitlines()
             if x.startswith("data:")]
    assert lines[0]["type"] == "thread" and lines[-1]["type"] == "final" and "messages" not in lines[-1]
    tid = lines[0]["thread_id"]
    thread = c.get(f"/projects/{pid}/threads/{tid}").json()
    assert thread["agent"] == "recall" and thread["messages"][-1]["citations"][0]["id"] == tickets
    assert [t["id"] for t in c.get(f"/projects/{pid}/threads").json()] == [tid]
    assert c.post(f"/projects/{pid}/agent", json={**body, "scope_id": 99999}).status_code == 400
    other = c.post("/projects", json={"name": "Other"}).json()["id"]
    assert c.get(f"/projects/{other}/threads/{tid}").status_code == 404


def test_tool_call_written_as_text_fails_over():
    from backend.core.llm.errors import LLMError
    from backend.core.llm.openai_compat import OpenAICompatProvider

    p = OpenAICompatProvider("x", "http://x", "m", key_env=None, timeout_s=1)
    with pytest.raises(LLMError):
        p._check_leak("<tool_call> <function=search_messages> <parameter=k> 10 </parameter>", [])
    p._check_leak("Abhishek forgot the tickets [[m:4]]", [])


def test_tool_call_on_the_last_step_still_ends_with_an_answer(project, monkeypatch):
    pid, chats, _ = project
    turns = [call("search_messages", query=f"q{i}") for i in range(6)]
    turns[-1].text = "Best I found: Abhishek."
    monkeypatch.setattr(agents, "router", lambda: FakeRouter(turns))
    ev = final(agents.run(pid, "recall", "who?", "chat", chats["College Friends"]))
    assert ev["text"] == "Best I found: Abhishek." and ev["steps"] == 6


def test_roast_target_is_the_full_name(project, monkeypatch):
    pid, chats, _ = project
    vn = mid("ek minute matlab")
    fake = FakeRouter([call("search_messages", query="voice"), say("roasts")],
                      structured=[{"target": "Rohan", "roasts": [{"text": "Rohan's minute lasts an hour", "evidence_ids": [vn]}]},
                                  {"verdicts": [{"index": 0, "safe": True, "problem": "", "rewrite": ""}]}])
    monkeypatch.setattr(agents, "router", lambda: fake)
    ev = final(agents.run(pid, "roaster", "roast Rohan's voice notes", "chat", chats["College Friends"]))
    assert ev["data"]["target"] == "Rohan Das" and ev["text"].startswith("**Rohan Das**")
