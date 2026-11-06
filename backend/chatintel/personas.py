"""Participant personas (F3.3): style, interests, humour, role and catchphrases, built from a sample of
the person's own messages plus their exact stats. Catchphrases must really repeat in the database and
example IDs must come from the sample, otherwise they are dropped.

chat_id=None builds the project-level persona from every chat the person is in.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from . import analytics, db, memory

log = logging.getLogger("addamind.personas")

SAMPLE_CHARS = 12000
TOP_N = 8


class Persona(BaseModel):
    summary: str = Field(description="two sentences on who this person is in the chat")
    communication_style: str = Field(description="how they write: length, language mix, emoji, voice notes, timing")
    interests: list[str] = Field(description="3 to 6 things they talk about")
    humour: str = Field(description="one sentence on their kind of humour, or 'rarely jokes'")
    group_role: str = Field(description="their role, under 10 words, e.g. 'the planner', 'the quiet one'")
    catchphrases: list[str] = Field(description="0 to 4 phrases they repeat, exactly as they write them")
    example_message_ids: list[int] = Field(description="3 to 5 IDs of messages most typical of them")


def _sample(rows) -> list:
    """Spread across time and favour longer messages and voice transcripts, within SAMPLE_CHARS."""
    if not rows:
        return []
    buckets = max(1, min(len(rows), 60))
    per = len(rows) / buckets
    picked = []
    for b in range(buckets):
        chunk = rows[int(b * per): int((b + 1) * per)] or rows[-1:]
        picked += sorted(chunk, key=lambda r: -len((r["text"] or "") + (r["media_result"] or "")))[:3]
    seen, out, size = set(), [], 0
    for r in sorted(picked, key=lambda r: (r["ts"], r["id"])):
        line = _line(r)
        if r["id"] in seen or size + len(line) > SAMPLE_CHARS:
            continue
        seen.add(r["id"])
        out.append((r, line))
        size += len(line) + 1
    return out


def _line(r) -> str:
    return f"[m:{r['id']}] {r['ts'][:16]} {db.media_line(r['kind'], r['text'], r['media_result'])[:280]}"


def _uses(con, pid: int, part_id: int, chat_id: int | None, phrase: str) -> int:
    like = memory._like(memory._norm_phrase(phrase))
    sql = ("SELECT COUNT(*) FROM messages m JOIN chats c ON c.id = m.chat_id AND c.project_id = ? "
           "LEFT JOIN media md ON md.message_id = m.id WHERE m.participant_id = ? "
           "AND (lower(m.text) LIKE ? ESCAPE '\\' OR lower(md.result) LIKE ? ESCAPE '\\')")
    args = [pid, part_id, like, like]
    if chat_id is not None:
        sql += " AND m.chat_id = ?"
        args.append(chat_id)
    return con.execute(sql, args).fetchone()[0]


def build(pid: int, part_id: int, chat_id: int | None = None) -> dict:
    with db.connect() as con:
        person = db._live_participant(con, pid, part_id)
        if not person:
            raise ValueError("participant not found")
        where, args = "m.participant_id = ? AND m.kind NOT IN ('system', 'call', 'deleted')", [part_id]
        if chat_id is not None:
            where += " AND m.chat_id = ?"
            args.append(chat_id)
        rows = con.execute(db.MSG_SELECT + f" WHERE {where} ORDER BY m.ts, m.id", (pid, *args)).fetchall()
        title = con.execute("SELECT title FROM chats WHERE id = ? AND project_id = ?",
                            (chat_id, pid)).fetchone() if chat_id is not None else None
    if not rows:
        raise ValueError("this person has no messages here")
    st = analytics.stats(pid, chat_id)
    me = next(p for p in st["participants"] if p["id"] == part_id)
    awards = [a["title"] for a in st["awards"] if a["participant_id"] == part_id]
    name = db.shown_name(person["name"], person["masked"])
    facts = {k: me[k] for k in ("messages", "share", "conversation_starts", "median_reply_s", "night_share",
                                "avg_text_length", "emoji", "media", "top_words")}
    facts["longest_silence_days"] = me["longest_silence"]["days"]
    facts["awards"] = awards
    chat_ids = [chat_id] if chat_id is not None else [c["id"] for c in db.list_chats(pid)]
    jokes = {j["phrase"]: j for c in chat_ids for j in ((memory.get_memory(pid, c) or {}).get("inside_jokes") or [])}
    with db.connect() as con:
        used = {phrase: _uses(con, pid, part_id, chat_id, phrase) for phrase in jokes}
    facts["inside_jokes"] = {p: {"times_they_used_it": n, "they_started_it": jokes[p]["started_by_id"] == part_id}
                             for p, n in used.items() if n}
    sample = _sample(rows)
    allowed = {r["id"] for r, _ in sample}
    where_txt = f"the chat '{title['title']}'" if title else "all their chats in this project"
    prompt = (f"Build a persona of {name} from {where_txt}.\nExact stats from the database (trust these):\n"
              f"{json.dumps(facts, ensure_ascii=False)}\n\nA sample of {len(sample)} of their {len(rows)} messages:\n" +
              "\n".join(line for _, line in sample))
    p = memory.cached_structured([prompt], prompt, Persona)
    with db.connect() as con:
        phrases = [c for c in p.catchphrases[:4] if 2 <= len(c) <= 40 and _uses(con, pid, part_id, chat_id, c) >= 2]
        counts = {c: _uses(con, pid, part_id, chat_id, c) for c in phrases}
    out = {"participant_id": part_id, "name": name, "chat_id": chat_id, "summary": p.summary,
           "communication_style": p.communication_style, "interests": p.interests[:6], "humour": p.humour,
           "group_role": p.group_role, "catchphrases": [{"phrase": c, "uses": counts[c]} for c in phrases],
           "example_message_ids": [i for i in p.example_message_ids if i in allowed][:5],
           "stats": facts, "based_on_messages": len(rows), "updated_at": db.now()}
    with db.connect() as con:
        con.execute("DELETE FROM personas WHERE participant_id = ? AND IFNULL(chat_id, 0) = ?", (part_id, chat_id or 0))
        con.execute("INSERT INTO personas(participant_id, chat_id, json, updated_at) VALUES (?, ?, ?, ?)",
                    (part_id, chat_id, json.dumps(out, ensure_ascii=False), out["updated_at"]))
    return out


def get(pid: int, part_id: int, chat_id: int | None = None, create: bool = True) -> dict | None:
    """The stored persona, or a new one when create is set (one model call, a few seconds)."""
    with db.connect() as con:
        if not db._live_participant(con, pid, part_id):
            return None
        if chat_id is not None and not con.execute("SELECT 1 FROM chats WHERE id = ? AND project_id = ?",
                                                   (chat_id, pid)).fetchone():
            return None
        r = con.execute("SELECT json FROM personas WHERE participant_id = ? AND IFNULL(chat_id, 0) = ?",
                        (part_id, chat_id or 0)).fetchone()
    if r:
        return json.loads(r["json"])
    return build(pid, part_id, chat_id) if create else None


def build_top(pid: int, chat_id: int, n: int = TOP_N, on_progress=None) -> dict:
    """Personas for the n most active people in a chat, 3 at a time. The rest are built on demand."""
    with db.connect() as con:
        ids = [r[0] for r in con.execute(
            "SELECT m.participant_id FROM messages m JOIN chats c ON c.id = m.chat_id "
            "WHERE m.chat_id = ? AND c.project_id = ? AND m.participant_id IS NOT NULL "
            "GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT ?", (chat_id, pid, n)).fetchall()]
    done, failed = 0, 0
    with ThreadPoolExecutor(3, thread_name_prefix="persona") as pool:
        for fut in [pool.submit(build, pid, i, chat_id) for i in ids]:
            try:
                fut.result()
                done += 1
            except Exception as e:  # noqa: BLE001 - one persona failing must not stop the rest
                log.warning("persona failed: %s", type(e).__name__)
                failed += 1
            if on_progress:
                on_progress(done + failed, len(ids))
    return {"personas": done, "personas_failed": failed}
