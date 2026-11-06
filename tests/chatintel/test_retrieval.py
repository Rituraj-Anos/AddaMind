import io
import zlib

import numpy as np
import pytest

from backend.chatintel import db, embeddings, ingest, retrieval
from backend.chatintel.retrieval import Scope

CHAT = """01/03/25, 9:00 pm - Priya Sen: Goa trip plan: 14 se 18 March, flight 6E-2134
01/03/25, 9:01 pm - Kabir Malhotra: pakka, main in hoon
01/03/25, 9:02 pm - Vikram Singh: main nahi aa paunga, exams
14/03/25, 4:12 am - Abhishek Kundu: BHAI TICKETS GHAR PE BHOOL GAYA
14/03/25, 4:13 am - Priya Sen: PNR se ho jayega, chill
20/04/25, 8:00 pm - Rohan Das: canteen mein Maggi kha rahe hain
"""
OTHER = """05/03/25, 10:00 am - Shrimant Roy: tickets book kar diye Mandarmani ke
05/03/25, 10:01 am - Suman Ghosh: thanks bhai
"""


def load(pid, name, text):
    job_id = ingest.create_job(pid, name)
    ingest.save_upload(io.BytesIO(text.encode()), pid, job_id)
    ingest.run_job(pid, job_id)
    job = db.get_job(pid, job_id)
    assert job["status"] == "done", job["error"]
    return job


def find(pid, mid_text):
    with db.connect() as con:
        return con.execute("SELECT id FROM messages WHERE text LIKE ?", (f"%{mid_text}%",)).fetchone()["id"]


def test_passages_built_once_per_message():
    pid = db.create_project("Suman")["id"]
    job = load(pid, "WhatsApp Chat with College Friends.txt", CHAT)
    assert job["stage"] == "done" and job["info"]["passages"] == 3  # 45-minute gaps split the chat three ways
    again = load(pid, "WhatsApp Chat with College Friends.txt", CHAT)
    assert again["info"]["passages"] == 0
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM messages WHERE passage_id IS NULL").fetchone()[0] == 0


def test_keyword_search_finds_planted_messages_without_embeddings():
    pid = db.create_project("Suman")["id"]
    load(pid, "WhatsApp Chat with College Friends.txt", CHAT)
    out = retrieval.search(Scope(pid), "who forgot the tickets")
    assert out["methods"] == ["keyword"] and out["results"][0]["id"] == find(pid, "TICKETS GHAR")
    goa = retrieval.search(Scope(pid), "Goa trip plan")
    assert goa["results"][0]["id"] == find(pid, "Goa trip plan")
    assert goa["results"][0]["chat_title"] == "College Friends"
    tickets = retrieval.search(Scope(pid), "tickets")["results"][0]["context"]
    assert f"[m:{find(pid, 'PNR')}] Priya Sen: PNR se ho jayega" in tickets  # neighbours carry their own IDs


def test_search_stays_in_scope():
    a = db.create_project("A")["id"]
    b = db.create_project("B")["id"]
    group = load(a, "WhatsApp Chat with College Friends.txt", CHAT)["chat_id"]
    load(a, "WhatsApp Chat - Shrimant Roy.txt", OTHER)
    assert retrieval.search(Scope(b), "tickets")["results"] == []
    in_group = retrieval.search(Scope(a, chat_id=group), "tickets")["results"]
    assert in_group and all(r["chat_id"] == group for r in in_group)
    both = {r["chat_title"] for r in retrieval.search(Scope(a), "tickets")["results"]}
    assert both == {"College Friends", "Shrimant Roy"}
    priya = next(p["id"] for p in db.list_participants(a) if p["name"] == "Priya Sen")
    assert all(r["participant_id"] == priya for r in retrieval.search(Scope(a, participant_id=priya), "goa tickets PNR")["results"])
    april = retrieval.search(Scope(a), "maggi tickets goa", since="2025-04-01")["results"]
    assert [r["text"] for r in april] == ["canteen mein Maggi kha rahe hain"]


def test_bad_query_text_is_inert():
    pid = db.create_project("A")["id"]
    load(pid, "WhatsApp Chat with College Friends.txt", CHAT)
    for q in ['" OR 1=1 --', "NEAR(goa", "tickets*)", "***"]:
        retrieval.search(Scope(pid), q)  # no FTS syntax error leaks out
    with pytest.raises(ValueError):
        retrieval.search(Scope(pid), "  ")


def _fake_vectors(texts, query):
    """Bag of words hashed into 64 buckets, with 'forgot' and 'bhool' sharing one: a tiny 'semantic' model."""
    out = []
    for t in texts:
        v = np.zeros(64)
        for w in t.casefold().replace("forgot", "bhool").split():
            v[zlib.crc32(w.encode()) % 64] += 1
        out.append(v.tolist())
    return out


def test_semantic_results_merge_and_fall_back(monkeypatch):
    monkeypatch.setenv("ADDAMIND_EMBEDDINGS", "on")
    calls = []

    def nvidia_down(texts, query):
        calls.append("nvidia")
        raise embeddings.EmbeddingError("nvidia 500")

    def gemini(texts, query):
        calls.append("gemini")
        return _fake_vectors(texts, query)

    monkeypatch.setattr(embeddings, "_CALL", {embeddings.NVIDIA: nvidia_down, embeddings.GEMINI: gemini})
    pid = db.create_project("Suman")["id"]
    job = load(pid, "WhatsApp Chat with College Friends.txt", CHAT)
    assert job["info"]["embedded"] == 3 and calls == ["nvidia", "gemini"]
    out = retrieval.search(Scope(pid), "who forgot")  # 'forgot' never appears in the chat
    assert out["methods"] == ["keyword", f"semantic ({embeddings.GEMINI})"]
    top = out["results"][0]
    assert top["id"] == find(pid, "TICKETS GHAR") and top["matched_by"] == ["semantic"]
    calls.clear()
    retrieval.search(Scope(pid), "who forgot")
    assert calls == []  # the query vector came from the cache
