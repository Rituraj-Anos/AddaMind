"""Agent tools over one project's chats. Each run gets ScopedTools, which sets the run's scope around
every call, so a chat-scoped run can't read other chats and nothing can read another project.

Messages are shown to the model as '[m:ID] date time · chat · Name: text'. Every [m:ID] a tool returns
is recorded for the run; the final answer may only cite those (checked in agents.py).
"""
from __future__ import annotations

import contextvars
import functools
import json
import re
from dataclasses import dataclass, field
from typing import Annotated

from backend.core.tools import ToolRegistry

from . import analytics, db, memory, personas, retrieval

TAG = re.compile(r"\[m:(\d+)\]")
chat_tools = ToolRegistry()


@dataclass
class Run:
    project_id: int
    chat_id: int | None = None  # chat scope
    participant_id: int | None = None  # participant scope
    seen: set[int] = field(default_factory=set)  # message IDs the tools returned


_run: contextvars.ContextVar[Run] = contextvars.ContextVar("addamind_run")


class ScopedTools(ToolRegistry):
    """The chat tools bound to one run: the scope is set around each call, in whatever thread runs it."""

    def __init__(self, run: Run):
        super().__init__()
        self._tools = chat_tools._tools
        self.run = run

    def execute(self, name, args, allowed=None):
        token = _run.set(self.run)
        try:
            return super().execute(name, args, allowed)
        finally:
            _run.reset(token)


def current() -> Run:
    try:
        return _run.get()
    except LookupError:
        raise RuntimeError("no active agent run") from None


def ctool(f):
    """Register a tool and record every [m:ID] in its result."""
    @functools.wraps(f)
    def wrapped(*a, **kw):
        out = f(*a, **kw)
        current().seen.update(int(x) for x in TAG.findall(json.dumps(out, ensure_ascii=False)))
        return out
    return chat_tools.tool(wrapped)


# ---------------------------------------------------------------- helpers
def _chat(chat_id: int | None) -> int | None:
    """The chat to read: the run's chat when scoped, else the requested one (checked against the project)."""
    run = current()
    if run.chat_id is not None:
        return run.chat_id
    if chat_id is None:
        return None
    if not db.get_chat(run.project_id, chat_id):
        raise ValueError(f"chat {chat_id} is not in this project; call list_chats")
    return chat_id


def _person(name: str | None, project_id: int | None = None) -> dict | None:
    """Participant by name, unique first name, or id. Raises with the options when it can't tell."""
    people = db.list_participants(project_id if project_id is not None else current().project_id)
    if not name:
        return None
    key = name.strip().lstrip("@").casefold()
    for p in people:
        if key in (p["name"].casefold(), str(p["id"])):
            return p
    firsts = [p for p in people if p["name"].split()[0].casefold() == key]
    if len(firsts) == 1:
        return firsts[0]
    raise ValueError(f"no single participant called '{name}'. Options: " + ", ".join(p["name"] for p in people[:25]))


def line(m: dict, chat_title: str | None = None) -> str:
    body = db.media_line(m["kind"], m["text"], (m.get("media") or {}).get("result"))
    who = m["sender"] or "(group event)"
    where = f" · {chat_title}" if chat_title else ""
    return f"[m:{m['id']}] {m['ts'][:16]}{where} · {who}: {body[:300]}"


def _ids(ids) -> list[str]:
    return [f"[m:{i}]" for i in ids or []]


def _chat_titles() -> dict[int, str]:
    return {c["id"]: c["title"] for c in db.list_chats(current().project_id)}


# ---------------------------------------------------------------- tools
@ctool
def list_chats() -> dict:
    """List the chats in this project with their kind, size and date range. Use first when the user
    doesn't say which chat, or to get chat ids for other tools."""
    run = current()
    chats = db.list_chats(run.project_id)
    if run.chat_id is not None:
        chats = [c for c in chats if c["id"] == run.chat_id]
    return {"chats": [{"chat_id": c["id"], "title": c["title"], "kind": c["kind"], "messages": c["message_count"],
                       "members": c["member_count"], "from": (c["first_ts"] or "")[:10], "to": (c["last_ts"] or "")[:10]}
                      for c in chats]}


@ctool
def list_participants(chat_id: Annotated[int | None, "Only people in this chat"] = None) -> dict:
    """List participants with message counts, who is 'me' (the user), and who opted out of roasts."""
    run = current()
    cid = _chat(chat_id)
    people = [p for p in db.list_participants(run.project_id) if cid is None or cid in p["chat_ids"]]
    return {"participants": [{"name": p["name"], "messages": p["message_count"], "is_me": p["is_me"],
                              "roast_opt_out": p["roast_opt_out"], "chats": len(p["chat_ids"])} for p in people[:40]]}


@ctool
def search_messages(query: Annotated[str, "What to look for, in the chat's own words when possible (Hinglish is fine)"],
                    chat_id: Annotated[int | None, "Limit to one chat"] = None,
                    participant: Annotated[str | None, "Only this person's messages (name)"] = None,
                    since: Annotated[str | None, "YYYY-MM-DD, inclusive"] = None,
                    until: Annotated[str | None, "YYYY-MM-DD, exclusive"] = None,
                    k: Annotated[int, "How many results, 1-10"] = 6) -> dict:
    """Search the chats (keywords plus meaning; voice notes, photos and videos are searchable through
    their transcripts and descriptions). Returns messages with nearby lines for context. Search again
    with other words if the first try misses."""
    run = current()
    pid = run.participant_id
    if participant and pid is None:
        pid = _person(participant)["id"]
    for d in (since, until):
        if d and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            raise ValueError("dates must be YYYY-MM-DD")
    out = retrieval.search(retrieval.Scope(run.project_id, _chat(chat_id), pid), query, max(1, min(k, 10)), since, until)
    titles = _chat_titles()
    results = []
    for r in out["results"]:
        results.append({"message": line(r, titles.get(r["chat_id"])), "context": r["context"]})
    return {"query": query, "results": results, "note": None if results else "nothing found; try other words"}


@ctool
def get_messages_around(message_id: Annotated[int, "A message id from another tool, the N in [m:N]"],
                        n: Annotated[int, "Messages before and after, 1-15"] = 5) -> dict:
    """Read the messages just before and after one message, to understand what it was replying to."""
    run = current()
    got = db.get_message(run.project_id, message_id, max(1, min(n, 15)))
    if not got or (run.chat_id is not None and got["message"]["chat_id"] != run.chat_id):
        raise ValueError("message not found in this scope")
    rows = got["before"] + [got["message"]] + got["after"]
    return {"chat": _chat_titles().get(got["message"]["chat_id"]), "lines": [line(m) for m in rows]}


@ctool
def get_chat_stats(chat_id: Annotated[int | None, "One chat; leave empty for the whole project"] = None) -> dict:
    """Exact counts from the database: messages per person, share, conversation starts, reply times,
    night messages, media by kind, emoji, longest silences, activity by hour and month, and rule-based
    awards. Use for any question about who talks most, who starts conversations, or habits."""
    run = current()
    cid = _chat(chat_id)
    s = analytics.stats(run.project_id, cid)
    people = s["participants"]
    if run.participant_id is not None:
        people = [p for p in people if p["id"] == run.participant_id] + [p for p in people if p["id"] != run.participant_id][:5]
    return {
        "totals": s["totals"], "busiest_day": s["activity"]["busiest_day"], "highlights": s["highlights"],
        "people": [{"name": p["name"], "messages": p["messages"], "share": p["share"],
                    "starts": p["conversation_starts"], "median_reply_s": p["median_reply_s"],
                    "night_messages": p["night_messages"], "avg_text_len": p["avg_text_length"], "emoji": p["emoji"],
                    "media": p["media"], "longest_silence_days": p["longest_silence"]["days"],
                    "silence_from": p["longest_silence"]["from"], "is_me": p["is_me"]} for p in people[:14]],
        "awards": [{"award": a["title"], "name": a["name"], "value": a["value"], "unit": a["unit"],
                    "evidence": _ids(a["message_ids"])} for a in s["awards"]],
        "messages_by_hour": s["activity"]["by_hour"],
        "top_words": s["top_words"][:10],
        "definitions": s["definitions"],
    }


@ctool
def get_reply_graph(chat_id: Annotated[int | None, "One chat; empty for the whole project"] = None) -> dict:
    """Who replies to whom within 10 minutes, plus @mentions: the strongest pairs and the closest duo."""
    run = current()
    g = analytics.graph(run.project_id, _chat(chat_id))
    names = {n["id"]: n["name"] for n in g["nodes"]}
    couple = g["power_couple"]
    return {"strongest": [f"{names[e['source']]} -> {names[e['target']]}: {e['replies']} replies, {e['mentions']} mentions"
                          for e in g["edges"][:15]],
            "closest_pair": couple and {"names": [names[i] for i in couple["participant_ids"]],
                                        "interactions": couple["interactions"]},
            "rule": g["rule"]}


def _memories(chat_id: int | None) -> list[tuple[int, dict]]:
    run = current()
    cid = _chat(chat_id)
    ids = [cid] if cid is not None else [c["id"] for c in db.list_chats(run.project_id)]
    return [(c, m) for c in ids if (m := memory.get_memory(run.project_id, c))]


@ctool
def get_mood_series(chat_id: Annotated[int | None, "One chat; empty for every chat"] = None) -> dict:
    """Mood per month from -1 (tense, sad) to 1 (happy), with the reason and evidence messages."""
    titles = _chat_titles()
    out = [{"chat": titles.get(c), "months": [{"month": x["month"], "mood": x["mood"], "reason": x["reason"],
                                                "messages": x["messages"], "evidence": _ids(x["message_ids"])}
                                               for x in m["mood"]]} for c, m in _memories(chat_id)]
    return {"series": out} if out else {"note": "memory is not built yet for this chat"}


@ctool
def get_timeline(chat_id: Annotated[int | None, "One chat; empty for every chat"] = None,
                 since: Annotated[str | None, "YYYY-MM-DD"] = None,
                 until: Annotated[str | None, "YYYY-MM-DD, exclusive"] = None) -> dict:
    """Key events in time order (trips, fights, results, people leaving), each with evidence messages,
    plus the chat's main topics."""
    titles = _chat_titles()
    out = []
    for c, m in _memories(chat_id):
        events = [e for e in m["timeline"] if (not since or e["date"] >= since) and (not until or e["date"] < until)]
        out.append({"chat": titles.get(c),
                    "events": [f"{e['date']} {e['title']}: {e['detail']} " + " ".join(_ids(e["message_ids"]))
                               for e in events[:40]],
                    "topics": [t["topic"] for t in m["topics"][:8]]})
    return {"timelines": out} if out else {"note": "memory is not built yet for this chat"}


@ctool
def get_inside_jokes(chat_id: Annotated[int | None, "One chat; empty for every chat"] = None) -> dict:
    """The chat's inside jokes, checked against the messages: who started each, when, and how often it's used."""
    titles = _chat_titles()
    out = [{"chat": titles.get(c), "phrase": j["phrase"], "meaning": j["meaning"], "started_by": j["started_by"],
            "first_used": j["first_date"], "uses": j["uses"], "first": f"[m:{j['first_message_id']}]",
            "examples": _ids(j["example_ids"])} for c, m in _memories(chat_id) for j in m["inside_jokes"]]
    return {"jokes": out}


@ctool
def get_persona(participant: Annotated[str, "Their name"],
                chat_id: Annotated[int | None, "Persona within one chat; empty for across all chats"] = None) -> dict:
    """How a person writes and behaves: style, interests, humour, role, catchphrases, stats and example messages."""
    run = current()
    p = _person(participant)
    cid = _chat(chat_id)
    got = personas.get(run.project_id, p["id"], cid)
    if not got:
        raise ValueError("no persona for that person here")
    return {k: got[k] for k in ("name", "summary", "communication_style", "interests", "humour", "group_role",
                                "catchphrases")} | {"stats": {k: v for k, v in got["stats"].items() if k != "top_words"},
                                                    "roast_opt_out": p["roast_opt_out"],
                                                    "examples": _ids(got["example_message_ids"])}


@ctool
def get_media(message_id: Annotated[int, "The N in [m:N] of a photo, voice note, video or document"]) -> dict:
    """What a photo shows, what a voice note says, or what a video or PDF contains."""
    run = current()
    got = db.get_message(run.project_id, message_id, 0)
    if not got or (run.chat_id is not None and got["message"]["chat_id"] != run.chat_id):
        raise ValueError("message not found in this scope")
    m = got["message"]
    if not m["media"]:
        return {"message": line(m), "media": "no media file for this message"}
    return {"message": line(m), "status": m["media"]["status"], "result": m["media"]["result"]}


ALL = chat_tools.names()
