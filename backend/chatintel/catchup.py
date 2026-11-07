"""Catch up: what happened in a chat while you were away, what needs your answer, and replies ready to send.

WhatsApp exports carry no read receipts, so "unread" starts after one of these points:
  auto    your last message here, or where you last marked the chat caught up, whichever is later
  upload  the first message the latest upload added (a newer export of the same chat)
  day     the last 24 hours before the chat's latest message
  time    a time you pick

Counts, people and @mentions come from SQL. The model only groups and explains, and every message ID it
returns must be one of the lines it was shown. Every @mention of you is listed, even if the model skips it.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from . import db, memory, personas
from .agents import strip_cites

Mode = Literal["auto", "upload", "day", "time"]
BUDGET = 40000  # characters of unread chat sent to the model (~10k tokens; the memory chain starts on Gemini)
LINE_CHARS = 280


# ---------------------------------------------------------------- where "unread" starts
def _me(con, pid: int) -> tuple[int, str, list[int]] | None:
    r = con.execute("SELECT id, name FROM participants WHERE project_id = ? AND is_me = 1 AND merged_into IS NULL",
                    (pid,)).fetchone()
    if not r:
        return None
    ids = [r["id"]] + [x[0] for x in con.execute("SELECT id FROM participants WHERE merged_into = ?", (r["id"],))]
    return r["id"], r["name"], ids


def _upload_start(con, cid: int) -> int | None:
    """First message the latest upload added, if this chat has been uploaded more than once."""
    rows = con.execute("SELECT info FROM jobs WHERE chat_id = ? AND status = 'done' ORDER BY id DESC", (cid,)).fetchall()
    if len(rows) < 2:
        return None
    return (json.loads(rows[0]["info"] or "{}")).get("first_new_id")


def _read_mark(con, cid: int, owner: str | None):
    return con.execute("SELECT m.ts, m.id FROM read_marks r JOIN messages m ON m.id = r.message_id "
                       "WHERE r.chat_id = ? AND r.owner = ?", (cid, owner or "")).fetchone()


def _window(con, pid: int, cid: int, mode: Mode, from_ts: str | None, owner: str | None) -> dict:
    """The SQL condition for unread messages, and a plain label for where they start."""
    me = _me(con, pid)
    last = con.execute("SELECT ts, id FROM messages WHERE chat_id = ? ORDER BY ts DESC, id DESC LIMIT 1", (cid,)).fetchone()
    my_last = None
    if me:
        q = ",".join("?" * len(me[2]))
        my_last = con.execute(f"SELECT ts, id FROM messages WHERE chat_id = ? AND participant_id IN ({q}) "
                              "ORDER BY ts DESC, id DESC LIMIT 1", (cid, *me[2])).fetchone()
    mark = _read_mark(con, cid, owner)
    upload = _upload_start(con, cid)
    options = {"auto": bool(my_last or mark), "upload": upload is not None, "day": last is not None, "time": True}

    if mode == "auto" and not (my_last or mark):
        mode = "day"  # nobody marked as you and no mark yet: the chat's last day is the closest guess
    if mode == "auto":
        start = max((x for x in (my_last, mark) if x), key=lambda r: (r["ts"], r["id"]))
        label = ("after you marked it caught up" if mark and start["id"] == mark["id"]
                 else "after your last message")
        where, args = "(m.ts, m.id) > (?, ?)", [start["ts"], start["id"]]
        since = start["ts"]
    elif mode == "upload":
        if upload is None:
            raise ValueError("this chat has only been uploaded once")
        where, args, label = "m.id >= ?", [upload], "added by the latest upload"
        since = None
    elif mode == "day":
        end = datetime.fromisoformat(last["ts"]) if last else datetime.now()
        since = (end - timedelta(hours=24)).isoformat(sep=" ", timespec="seconds")
        where, args, label = "m.ts > ?", [since], "in the chat's last 24 hours"
    else:
        try:
            since = datetime.fromisoformat((from_ts or "").replace("T", " ")).isoformat(sep=" ", timespec="seconds")
        except ValueError:
            raise ValueError("pick a time like 2026-01-31 21:00") from None
        where, args, label = "m.ts >= ?", [since], "since the time you picked"
    return {"mode": mode, "where": where, "args": args, "label": label, "since": since, "options": options,
            "me": {"id": me[0], "name": me[1], "ids": me[2]} if me else None,
            "my_last_ts": my_last["ts"] if my_last else None}


def _unread_rows(con, pid: int, cid: int, w: dict):
    return con.execute(db.MSG_SELECT + f" WHERE m.chat_id = ? AND {w['where']} AND m.kind != 'call' "
                       "ORDER BY m.ts, m.id", (pid, cid, *w["args"])).fetchall()


def _names_me(text: str | None, first: str) -> bool:
    return bool(text and first and re.search(rf"(?<!\w){re.escape(first)}(?!\w)", text, re.IGNORECASE))


# ---------------------------------------------------------------- the counts (no model)
def summary(pid: int, cid: int, mode: Mode = "auto", from_ts: str | None = None, owner: str | None = None) -> dict | None:
    """How many messages are unread from the chosen point, who sent them, and which ones mention you."""
    with db.connect() as con:
        chat = db.get_chat(pid, cid)
        if not chat:
            return None
        w = _window(con, pid, cid, mode, from_ts, owner)
        rows = _unread_rows(con, pid, cid, w)
        me = w["me"]
        mine = set(me["ids"]) if me else set()
        ids = [r["id"] for r in rows]
        mentioned = set()
        if me and ids:
            q = ",".join("?" * len(ids))
            mentioned = {x[0] for x in con.execute(
                f"SELECT message_id FROM message_mentions WHERE participant_id IN ({','.join('?' * len(mine))}) "
                f"AND message_id IN ({q})", (*mine, *ids))}
    others = [r for r in rows if r["participant_id"] not in mine]
    first = me["name"].split()[0] if me else ""
    mentions = [r["id"] for r in others if r["id"] in mentioned or _names_me(r["text"], first)]
    by = Counter((r["participant_id"], db.shown_name(r["sender"], r["masked"])) for r in others if r["sender"])
    kinds = Counter(r["kind"] for r in others if r["kind"] not in ("text", "system", "deleted"))
    return {"chat": {"id": chat["id"], "title": chat["title"], "kind": chat["kind"]},
            "mode": w["mode"], "label": w["label"], "since": w["since"], "options": w["options"],
            "me": {"id": me["id"], "name": me["name"]} if me else None, "my_last_ts": w["my_last_ts"],
            "unread": len(others), "yours_in_window": len(rows) - len(others),
            "first_ts": others[0]["ts"] if others else None, "last_ts": others[-1]["ts"] if others else None,
            "last_message_id": rows[-1]["id"] if rows else None,
            "senders": [{"participant_id": p, "name": n, "messages": c} for (p, n), c in by.most_common(8)],
            "people": len(by), "media": dict(kinds), "mentions": mentions}


# ---------------------------------------------------------------- the read (one model call, cached)
class Topic(BaseModel):
    title: str = Field(description="under 8 words")
    summary: str = Field(description="one or two sentences: what was said and who said it")
    message_ids: list[int] = Field(description="1 to 4 IDs of the messages that show it")


class NeedsYou(BaseModel):
    message_id: int = Field(description="the message the user should answer")
    why: str = Field(description="under 12 words, e.g. 'asks if you are coming on Saturday'")
    replies: list[str] = Field(description="2 or 3 replies ready to send, in the user's own style and language mix")


class Decision(BaseModel):
    text: str = Field(description="one sentence: what was decided or planned, with day, time or place if given")
    message_ids: list[int] = Field(description="1 to 3 IDs")


class CatchupRead(BaseModel):
    tldr: str = Field(description="two or three sentences: what you missed, most important first")
    topics: list[Topic] = Field(description="2 to 6 conversations that happened, in time order")
    needs_you: list[NeedsYou] = Field(description="0 to 6 messages that ask the user something, mention them, or "
                                                  "wait on their answer. Empty if nothing needs them.")
    decisions: list[Decision] = Field(description="0 to 5 plans or decisions made")


def _transcript(rows, keep_ids: set[int]) -> tuple[str, set[int], bool]:
    """Unread lines within BUDGET. Over budget, keeps messages to the user, questions and media first."""
    def line(r):
        body = (f"(event) {db.redact(r['text'])}" if r["kind"] == "system" else
                f"{db.shown_name(r['sender'], r['masked'])}: {db.media_line(r['kind'], r['text'], r['media_result'])}")
        return f"[m:{r['id']}] {r['ts'][5:16]} {body[:LINE_CHARS]}"
    lines = [(r, line(r)) for r in rows]
    sampled = sum(len(t) + 1 for _, t in lines) > BUDGET
    if sampled:
        rank = sorted(range(len(lines)), key=lambda i: (lines[i][0]["id"] not in keep_ids,
                                                        "?" not in (lines[i][0]["text"] or ""),
                                                        not lines[i][0]["media_result"], -len(lines[i][1])))
        chosen, size = set(), 0
        for i in rank:
            if size + len(lines[i][1]) < BUDGET:
                chosen.add(i)
                size += len(lines[i][1]) + 1
        lines = [x for i, x in enumerate(lines) if i in chosen]
    return "\n".join(t for _, t in lines), {r["id"] for r, _ in lines}, sampled


def _style(pid: int, cid: int, me: dict, con) -> str:
    """How the user writes: their persona if one exists, plus a few of their own recent messages."""
    p = personas.get(pid, me["id"], cid, create=False) or personas.get(pid, me["id"], None, create=False)
    q = ",".join("?" * len(me["ids"]))
    own = con.execute(f"SELECT text FROM messages WHERE chat_id = ? AND participant_id IN ({q}) AND kind = 'text' "
                      "AND length(text) BETWEEN 2 AND 160 ORDER BY ts DESC, id DESC LIMIT 12", (cid, *me["ids"])).fetchall()
    style = f"How {me['name']} writes: {p['communication_style']}\n" if p else ""
    if own:
        style += f"Some of {me['name']}'s own recent messages:\n" + "\n".join(f"- {r['text']}" for r in own)
    return style or f"{me['name']} has no messages here yet: keep replies short and casual."


def read(pid: int, cid: int, mode: Mode = "auto", from_ts: str | None = None, owner: str | None = None) -> dict | None:
    s = summary(pid, cid, mode, from_ts, owner)
    if s is None or not s["unread"]:
        return s and {**s, "tldr": None, "topics": [], "needs_you": [], "decisions": [], "sampled": False}
    with db.connect() as con:
        w = _window(con, pid, cid, s["mode"], from_ts, owner)
        rows = _unread_rows(con, pid, cid, w)
        me = w["me"]
        style = _style(pid, cid, me, con) if me else ""
    mentions = set(s["mentions"])
    transcript, shown, sampled = _transcript(rows, mentions)
    who = (f"The user is {me['name']}. Their own messages are part of the lines; never list those as needing them."
           if me else "Nobody is marked as the user, so leave needs_you empty.")
    kind = "group chat" if s["chat"]["kind"] == "group" else "one-to-one chat"
    must = [i for i in s["mentions"] if i in shown]
    must_line = (f"These lines mention the user by name; each one must be in needs_you with replies: "
                 f"{', '.join(f'[m:{i}]' for i in must)}.\n" if must else "")
    prompt = (f"Chat: {s['chat']['title']} ({kind}). The user was away and has {s['unread']} unread messages "
              f"{s['label']}{', the most relevant ones shown' if sampled else ''}.\n{who}\n{style}\n\n"
              f"Unread lines:\n{transcript}\n\n{must_line}"
              "Catch the user up. In needs_you, also list open questions or plans that wait on everyone's answer "
              "(who is coming, when, which option), latest first, if the user hasn't answered them in these lines. "
              "Replies answer exactly that message, sound like the user, and never invent plans or facts that the "
              "lines don't show.")
    out = memory.cached_structured([prompt], prompt, CatchupRead)
    by_id = {r["id"]: r for r in rows}
    mine = set(me["ids"]) if me else set()

    def ok(ids):
        return [i for i in ids if i in shown][:4]

    needs, seen = [], set()
    for n in out.needs_you:
        r = by_id.get(n.message_id)
        if r and n.message_id in shown and r["participant_id"] not in mine and n.message_id not in seen:
            seen.add(n.message_id)
            said = re.sub(r"@\S+(\s\S+)?\s*", "", (r["text"] or "")).strip().casefold()
            replies = [t for t in dict.fromkeys(strip_cites(x).strip() for x in n.replies)
                       if t and t.casefold() not in (said, (r["text"] or "").strip().casefold())][:3]  # no echoes
            needs.append({"message": db.message_json(r), "why": strip_cites(n.why), "replies": replies, "source": "read"})
    for mid in s["mentions"]:  # every @mention of the user is listed, even if the model left it out
        if mid not in seen and mid in by_id:
            needs.append({"message": db.message_json(by_id[mid]), "why": "mentions you", "replies": [], "source": "mention"})
    needs.sort(key=lambda n: (n["message"]["ts"], n["message"]["id"]))
    topics = [{"title": t.title, "summary": strip_cites(t.summary), "message_ids": ok(t.message_ids)}
              for t in out.topics if ok(t.message_ids)][:6]
    decisions = [{"text": strip_cites(d.text), "message_ids": ok(d.message_ids)[:3]}
                 for d in out.decisions if ok(d.message_ids)][:5]
    return {**s, "tldr": strip_cites(out.tldr), "topics": topics, "needs_you": needs, "decisions": decisions,
            "sampled": sampled}


def mark_read(pid: int, cid: int, message_id: int, owner: str | None) -> bool:
    """Remember where this visitor caught up to in this chat."""
    with db.connect() as con:
        if not con.execute("SELECT 1 FROM messages m JOIN chats c ON c.id = m.chat_id "
                           "WHERE m.id = ? AND m.chat_id = ? AND c.project_id = ?", (message_id, cid, pid)).fetchone():
            return False
        con.execute("INSERT OR REPLACE INTO read_marks(chat_id, owner, message_id, updated_at) VALUES (?, ?, ?, ?)",
                    (cid, owner or "", message_id, db.now()))
    return True
