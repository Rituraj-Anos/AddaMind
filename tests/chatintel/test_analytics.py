import io

import pytest

from backend.chatintel import analytics, db, ingest

# 8 counted messages. Gaps: 2 min, 1 min, 27 min, 1 min, then >2 h breaks before rows 6, 7 and 9.
CHAT = """01/03/25, 10:00 am - Priya Sen created group "Test"
01/03/25, 10:00 am - Priya Sen: plan kya hai 😂😂
01/03/25, 10:02 am - Rohan Das: PTT-20250301-WA0001.opus (file attached)
01/03/25, 10:03 am - Priya Sen: @\u2068Rohan Das\u2069 bol na
01/03/25, 10:30 am - Kabir Malhotra: goa chalein
01/03/25, 10:31 am - Kabir Malhotra: goa chalein pakka
02/03/25, 1:15 am - Kabir Malhotra: neend nahi aa rahi
02/03/25, 3:00 pm - Priya Sen: goa tickets
02/03/25, 4:00 pm - Kabir Malhotra left
10/03/25, 9:00 pm - Rohan Das: ek minute
"""


@pytest.fixture()
def chat(tmp_path, monkeypatch):
    monkeypatch.setenv("ADDAMIND_DATA", str(tmp_path))
    pid = db.create_project("Suman")["id"]
    job_id = ingest.create_job(pid, "WhatsApp Chat with Test.txt")
    ingest.save_upload(io.BytesIO(CHAT.encode()), pid, job_id)
    ingest.run_job(pid, job_id)
    return pid, db.get_job(pid, job_id)["chat_id"]


def by_name(s):
    return {p["name"]: p for p in s["participants"]}


def test_exact_counts(chat):
    pid, cid = chat
    s = analytics.stats(pid, cid)
    assert s["totals"]["messages"] == 8 and s["totals"]["conversations"] == 4
    assert s["totals"]["media"] == {"voice": 1} and s["totals"]["active_days"] == 3
    p = by_name(s)
    assert [p[n]["messages"] for n in ("Priya Sen", "Kabir Malhotra", "Rohan Das")] == [3, 3, 2]
    assert [p[n]["conversation_starts"] for n in ("Priya Sen", "Kabir Malhotra", "Rohan Das")] == [2, 1, 1]
    assert (p["Rohan Das"]["median_reply_s"], p["Priya Sen"]["median_reply_s"], p["Kabir Malhotra"]["median_reply_s"]) == (120, 60, 1620)
    assert p["Priya Sen"]["share"] == 0.375 and p["Priya Sen"]["emoji"] == 2
    assert p["Kabir Malhotra"]["night_messages"] == 1 and p["Rohan Das"]["media"] == {"voice": 1}
    assert s["activity"]["busiest_day"] == {"date": "2025-03-01", "messages": 5}
    assert s["activity"]["by_hour"][10] == 5 and s["activity"]["by_weekday"][5] == 5  # 1 Mar 2025 was a Saturday
    assert s["top_words"][:2] == [("goa", 3), ("chalein", 2)]  # names and stopwords are left out
    assert s["highlights"]["conversation_starter"]["name"] == "Priya Sen"
    assert s["highlights"]["voice_note_king"] == {"participant_id": p["Rohan Das"]["id"], "name": "Rohan Das", "voice_notes": 1}


def test_silence_and_awards(chat):
    pid, cid = chat
    s = analytics.stats(pid, cid)
    rohan = by_name(s)["Rohan Das"]["longest_silence"]
    assert (rohan["days"], rohan["from"], rohan["to"]) == (9.5, "2025-03-01 10:02:00", "2025-03-10 21:00:00")
    priya = by_name(s)["Priya Sen"]["longest_silence"]
    assert priya["days"] == 8.2 and priya["until_end"]
    awards = {a["award"]: a for a in s["awards"]}
    assert awards["ghost"]["name"] == "Rohan Das" and awards["ghost"]["value"] == 9.5
    assert awards["night_owl"]["name"] == "Kabir Malhotra" and awards["night_owl"]["value"] == 1
    assert awards["hype_machine"]["name"] == "Priya Sen" and awards["lurker"]["name"] == "Rohan Das"
    assert "speed_replier" not in awards and "essayist" not in awards  # under the minimum sample
    with db.connect() as con:  # every cited message id exists and is the person's own
        for a in s["awards"]:
            for mid in a["message_ids"]:
                assert con.execute("SELECT participant_id FROM messages WHERE id = ?", (mid,)).fetchone()[0] == a["participant_id"]


def test_reply_graph(chat):
    pid, cid = chat
    g = analytics.graph(pid, cid)
    ids = {n["name"]: n["id"] for n in g["nodes"]}
    edges = {(e["source"], e["target"]): (e["replies"], e["mentions"]) for e in g["edges"]}
    assert edges == {(ids["Rohan Das"], ids["Priya Sen"]): (1, 0), (ids["Priya Sen"], ids["Rohan Das"]): (1, 1)}
    assert g["power_couple"]["interactions"] == 3
    assert set(g["power_couple"]["participant_ids"]) == {ids["Priya Sen"], ids["Rohan Das"]}


def test_project_scope_and_isolation(chat):
    pid, cid = chat
    other = db.create_project("Other")["id"]
    assert analytics.stats(other, cid) is None and analytics.graph(other, cid) is None
    assert analytics.stats(other)["totals"]["messages"] == 0
    assert analytics.stats(pid)["totals"]["messages"] == 8
