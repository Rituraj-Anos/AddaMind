import io
import re

import pytest

from backend.chatintel import db, ingest, memory, personas

CHAT = """01/03/25, 9:00 pm - Priya Sen: Goa plan final? 14 se 18 March
01/03/25, 9:01 pm - Rohan Das: ek minute, main pakka in
01/03/25, 9:02 pm - Kabir Malhotra: Rohan ka ek minute matlab 5 minute 😂
01/03/25, 9:03 pm - Priya Sen: bhai ek minute mat bolna please
14/03/25, 4:12 am - Abhishek Kundu: BHAI TICKETS GHAR PE BHOOL GAYA
12/05/25, 1:10 am - Kabir Malhotra: kal DBMS hai aur kuch nahi padha 😭
12/05/25, 1:12 am - Rohan Das: ek minute, mera bhi same
12/05/25, 1:14 am - Priya Sen: ye group best hai honestly
12/05/25, 1:15 am - Priya Sen: ye group best hai honestly
12/05/25, 1:16 am - Kabir Malhotra: ye group best hai honestly
"""
NEWER = CHAT + "02/06/25, 8:00 pm - Rohan Das: ek minute, result aaya?\n"


def ids_in(prompt):
    return [int(x) for x in re.findall(r"\[m:(\d+)\]", prompt)]


@pytest.fixture()
def fake(monkeypatch):
    monkeypatch.setenv("ADDAMIND_MEMORY", "on")
    calls = []

    def structured(prompt, schema, **kw):
        calls.append((schema.__name__, prompt))
        ids = ids_in(prompt)
        if schema is memory.MonthSummary:
            may = "2025-05" in prompt
            return schema(topics=["exams" if may else "Goa"], mood=-0.7 if may else 0.9,
                          mood_reason="exam stress" if may else "trip excitement", mood_message_ids=ids[:1] + [99999],
                          events=[memory.Event(title="Exam night" if may else "Goa planned", detail="d",
                                               people=["Kabir", "Priya Sen", "Nobody Here"], message_ids=[ids[-1], 99999]),
                                  memory.Event(title="Made up", detail="d", people=[], message_ids=[123456])],
                          joke_candidates=[memory.JokeCandidate(phrase="ek minute mat", meaning="Rohan's long voice notes"),
                                           memory.JokeCandidate(phrase="ye group best hai honestly", meaning="filler"),
                                           memory.JokeCandidate(phrase="flying penguins", meaning="never said")],
                          dynamics="Priya drives the chat.")
        if schema is memory.Dynamics:
            return schema(overview="o", patterns=["p"], roles=[memory.Role(name="Priya", role="the planner")],
                          relationships=[memory.Relationship(people=["Priya Sen", "Rohan Das"], description="r",
                                                             message_ids=[ids_in(prompt)[0] if ids_in(prompt) else 1, 424242]),
                                         memory.Relationship(people=["Priya Sen", "Ghost Person"], description="x",
                                                             message_ids=[])])
        if schema is personas.Persona:
            return schema(summary="s", communication_style="c", interests=["i"], humour="h", group_role="the delay",
                          catchphrases=["ek minute", "never said this"], example_message_ids=ids[:2] + [777777])
        raise AssertionError(schema)

    monkeypatch.setattr(memory, "structured", structured)
    return calls


def load(pid, text):
    job_id = ingest.create_job(pid, "WhatsApp Chat with College Friends.txt")
    ingest.save_upload(io.BytesIO(text.encode()), pid, job_id)
    ingest.run_job(pid, job_id)
    job = db.get_job(pid, job_id)
    assert job["status"] == "done", job["error"]
    return job


def msg_id(pid, text):
    with db.connect() as con:
        return con.execute("SELECT id FROM messages WHERE text = ?", (text,)).fetchone()["id"]


def test_memory_is_grounded(fake):
    pid = db.create_project("Suman")["id"]
    cid = load(pid, CHAT)["chat_id"]
    m = memory.get_memory(pid, cid)
    assert [(x["month"], x["mood"]) for x in m["mood"]] == [("2025-03", 0.9), ("2025-05", -0.7)]
    assert all(99999 not in x["message_ids"] for x in m["mood"])
    assert [e["title"] for e in m["timeline"]] == ["Goa planned", "Exam night"]  # the made-up event is gone
    goa = m["timeline"][0]
    assert goa["date"] == "2025-03-14" and goa["message_ids"] == [msg_id(pid, "BHAI TICKETS GHAR PE BHOOL GAYA")]
    assert goa["people"] == ["Kabir Malhotra", "Priya Sen"]  # first name resolved, unknown name dropped
    jokes = {j["phrase"]: j for j in m["inside_jokes"]}
    # "ek minute mat" is used once, but its core "ek minute" repeats: kept, with the first use from SQL.
    assert set(jokes) == {"ek minute"}  # copy-pasted filler and the never-said phrase are dropped
    assert jokes["ek minute"]["started_by"] == "Rohan Das" and jokes["ek minute"]["uses"] == 4
    assert jokes["ek minute"]["first_message_id"] == msg_id(pid, "ek minute, main pakka in")
    rels = m["dynamics"]["relationships"]
    assert len(rels) == 1 and 424242 not in rels[0]["message_ids"]
    assert m["dynamics"]["roles"] == [{"name": "Priya Sen", "role": "the planner"}]


def test_persona_keeps_only_verified_claims(fake):
    pid = db.create_project("Suman")["id"]
    cid = load(pid, CHAT)["chat_id"]
    rohan = next(p["id"] for p in db.list_participants(pid) if p["name"] == "Rohan Das")
    p = personas.get(pid, rohan, cid)
    assert p["catchphrases"] == [{"phrase": "ek minute", "uses": 2}]
    assert 777777 not in p["example_message_ids"] and p["example_message_ids"]
    assert p["stats"]["messages"] == 2 and p["stats"]["inside_jokes"] == {
        "ek minute": {"times_they_used_it": 2, "they_started_it": True}}
    prompt = next(pr for name, pr in fake if name == "Persona" and "Rohan Das" in pr)
    assert "Priya Sen:" not in prompt  # only their own messages are sampled
    assert personas.get(pid, rohan, cid)["updated_at"] == p["updated_at"]  # stored, not rebuilt
    other = db.create_project("Other")["id"]
    assert personas.get(other, rohan, cid) is None


def test_newer_export_resummarises_only_new_months(fake):
    pid = db.create_project("Suman")["id"]
    load(pid, CHAT)
    months_before = sum(1 for name, _ in fake if name == "MonthSummary")
    load(pid, NEWER)
    new = [pr for name, pr in fake if name == "MonthSummary"][months_before:]
    assert months_before == 2 and len(new) == 1 and "Month: 2025-06" in new[0]
    load(pid, NEWER)  # nothing new: no summaries at all
    assert sum(1 for name, _ in fake if name == "MonthSummary") == 3


def test_summaries_are_cached_by_content(fake):
    pid = db.create_project("Suman")["id"]
    cid = load(pid, CHAT)["chat_id"]
    n = len(fake)
    memory.build_memory(pid, cid, months=["2025-03", "2025-05"])
    assert sum(1 for name, _ in fake[n:] if name == "MonthSummary") == 0


def test_busy_month_is_sampled_within_budget(monkeypatch):
    monkeypatch.setattr(memory, "MONTH_BUDGET", 300)
    rows = [{"id": i, "ts": f"2025-03-0{1 + i // 10} 10:{i % 60:02d}:00", "kind": "text", "text": "x" * (5 + i),
             "sender": "A", "masked": 0, "media_result": None} for i in range(40)]
    text, ids, sampled = memory._transcript(rows)
    assert sampled and len(text) <= 300 + 40 and 39 in ids and 0 not in ids  # longest kept, in time order
    assert ids_in(text) == sorted(ids_in(text))
