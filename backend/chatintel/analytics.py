"""Exact chat statistics, reply graph and awards for a chat or a whole project. No model involved."""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import db
from .parser import MEDIA_KINDS

GAP = timedelta(hours=2)
REPLY_WINDOW = timedelta(minutes=10)
NIGHT_HOURS = range(0, 4)
MIN_SAMPLE = 10  # replies or text messages needed before a median or average counts for an award

# Sent with every stats result, so the agents explain numbers the same way the code counts them.
DEFINITIONS = """\
- A conversation starts with the first message after 2 hours of silence in that chat.
- A reply is a message from a different person right after someone else's, inside a conversation.
  Median reply time uses those gaps. The reply graph counts replies within 10 minutes plus @mentions.
- Night messages are sent between 00:00 and 03:59.
- Longest silence is the longest gap between one person's messages in a chat, or from their last
  message to the chat's last message.
- System lines (joins, leaves, calls) are not counted as messages."""

# shortcut: covers the common emoji blocks, not every ZWJ sequence as one emoji; fine for counting habits.
_EMOJI = re.compile("[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\u231A\u231B\u23E9-\u23FA]")
_WORD = re.compile(r"[a-z\u0900-\u097f\u0980-\u09ff']{3,}")
_URL = re.compile(r"https?://\S+|@\S+")
STOPWORDS = set("""
the and for are but not you your yours with this that have has had was were will would can could should just
what when where who why how all any its it's our out from they them their there then than too very also into
about been being because did does doing done each few more most other some such only own same off over under
again once here both him his her hers she he me my mine we us i'm i've i'll don't didn't can't won't isn't it's
yes yeah yep nope okay ok lol haha hahaha hmm umm omg please thanks thank like get got going gonna wanna let
one two now today tomorrow yesterday tonight really well even still know think see say said make made
hai hain ka ki ke ko se na nahi nhi toh bhi kya ho hoga hogi main mein mai tu tum tera teri tere mera meri mere
aur ye yeh wo woh haan han nahin kar karo karna kara kiya raha rahi rahe tha thi the bhai bro yaar abhi kal aaj
kuch koi sab bas bol bolo acha accha theek thik pe par ek jo jab tab kab kaise kyun kyu hum humko mujhe tujhe
use usko unko apna apni apne wala wali wale diya liya lena dena dekh dekho chal chalo sun suno baat
""".split())


@dataclass
class _P:
    id: int
    name: str
    is_me: bool
    messages: int = 0
    starts: int = 0
    reply_s: list[float] = field(default_factory=list)
    night_ids: list[int] = field(default_factory=list)
    text_lens: list[tuple[int, int]] = field(default_factory=list)  # (length, message id)
    emoji: int = 0
    emoji_best: tuple[int, int] = (0, 0)  # (emoji count, message id)
    media: Counter = field(default_factory=Counter)
    words: Counter = field(default_factory=Counter)
    hours: list[int] = field(default_factory=lambda: [0] * 24)
    silence: tuple[timedelta, int | None, int | None, datetime | None, datetime | None] = (timedelta(0), None, None, None, None)
    ids: list[int] = field(default_factory=list)


def _load(pid: int, chat_id: int | None):
    with db.connect() as con:
        where, args = "c.project_id = ?", [pid]
        if chat_id is not None:
            chat = con.execute("SELECT id, title FROM chats WHERE id = ? AND project_id = ?", (chat_id, pid)).fetchone()
            if not chat:
                return None
            where, args = where + " AND m.chat_id = ?", args + [chat_id]
            people = con.execute("SELECT p.id, p.name, p.masked, p.is_me FROM participants p JOIN chat_members cm "
                                 "ON cm.participant_id = p.id WHERE cm.chat_id = ? AND p.project_id = ?",
                                 (chat_id, pid)).fetchall()
        else:
            chat = None
            people = con.execute("SELECT id, name, masked, is_me FROM participants WHERE project_id = ? "
                                 "AND merged_into IS NULL", (pid,)).fetchall()
        rows = con.execute(f"SELECT m.id, m.chat_id, m.participant_id, m.ts, m.kind, m.text FROM messages m "
                           f"JOIN chats c ON c.id = m.chat_id WHERE {where} ORDER BY m.chat_id, m.ts, m.id", args).fetchall()
        mentions = con.execute(f"SELECT mm.message_id, mm.participant_id FROM message_mentions mm JOIN messages m "
                               f"ON m.id = mm.message_id JOIN chats c ON c.id = m.chat_id WHERE {where}", args).fetchall()
    return chat, people, rows, mentions


def _compute(pid: int, chat_id: int | None):
    loaded = _load(pid, chat_id)
    if loaded is None:
        return None
    chat, people, rows, mentions = loaded
    per = {r["id"]: _P(r["id"], db.shown_name(r["name"], r["masked"]), bool(r["is_me"])) for r in people}
    skip = STOPWORDS | {w for r in people for w in _WORD.findall(r["name"].casefold())}  # names aren't topics
    hours, weekdays, days = [0] * 24, [0] * 7, Counter()
    media, words, emoji = Counter(), Counter(), Counter()
    replies: Counter[tuple[int, int]] = Counter()  # (replier, replied to)
    sender_of: dict[int, int] = {}
    last_seen: dict[tuple[int, int], tuple[datetime, int]] = {}
    chat_end: dict[int, datetime] = {}
    prev = None
    for r in rows:
        if r["participant_id"] not in per or r["kind"] in ("system", "call"):
            continue  # system lines neither count nor break a conversation
        ts, p, cid = datetime.fromisoformat(r["ts"]), per[r["participant_id"]], r["chat_id"]
        if prev and prev[0] != cid:
            prev = None
        sender_of[r["id"]] = p.id
        p.messages += 1
        p.ids.append(r["id"])
        p.hours[ts.hour] += 1
        hours[ts.hour] += 1
        weekdays[ts.weekday()] += 1
        days[ts.date().isoformat()] += 1
        if prev is None or ts - prev[1] >= GAP:
            p.starts += 1
        elif prev[2] != p.id:
            p.reply_s.append((ts - prev[1]).total_seconds())
            if ts - prev[1] <= REPLY_WINDOW:
                replies[(p.id, prev[2])] += 1
        if ts.hour in NIGHT_HOURS:
            p.night_ids.append(r["id"])
        if r["kind"] in MEDIA_KINDS:
            p.media[r["kind"]] += 1
            media[r["kind"]] += 1
        text = r["text"] or ""
        found = _EMOJI.findall(text)
        if found:
            p.emoji += len(found)
            emoji.update(found)
            p.emoji_best = max(p.emoji_best, (len(found), r["id"]))
        if r["kind"] == "text" and text:
            p.text_lens.append((len(text), r["id"]))
            w = [x for x in _WORD.findall(_URL.sub(" ", text.casefold())) if x not in skip]
            p.words.update(w)
            words.update(w)
        key = (cid, p.id)
        if key in last_seen and ts - last_seen[key][0] > p.silence[0]:
            p.silence = (ts - last_seen[key][0], last_seen[key][1], r["id"], last_seen[key][0], ts)
        last_seen[key] = (ts, r["id"])
        chat_end[cid] = ts
        prev = (cid, ts, p.id)
    for (cid, person), (ts, mid) in last_seen.items():  # silence that runs to the end of the chat
        p = per[person]
        if chat_end[cid] - ts > p.silence[0]:
            p.silence = (chat_end[cid] - ts, mid, None, ts, chat_end[cid])

    mention_counts: Counter[tuple[int, int]] = Counter()
    for m in mentions:
        src = sender_of.get(m["message_id"])
        if src is not None and m["participant_id"] in per and m["participant_id"] != src:
            mention_counts[(src, m["participant_id"])] += 1
    return chat, per, rows, dict(hours=hours, weekdays=weekdays, days=days, media=media, words=words, emoji=emoji,
                                 replies=replies, mentions=mention_counts)


def _median(xs):
    return round(statistics.median(xs)) if xs else None


def _avg_len(p: _P):
    return round(sum(n for n, _ in p.text_lens) / len(p.text_lens), 1) if p.text_lens else None


def _person(p: _P, total: int) -> dict:
    gap, from_id, to_id, from_ts, to_ts = p.silence
    return {
        "id": p.id, "name": p.name, "is_me": p.is_me, "messages": p.messages,
        "share": round(p.messages / total, 4) if total else 0.0,
        "conversation_starts": p.starts, "replies": len(p.reply_s), "median_reply_s": _median(p.reply_s),
        "mean_reply_s": round(statistics.fmean(p.reply_s)) if p.reply_s else None,
        "night_messages": len(p.night_ids), "night_share": round(len(p.night_ids) / p.messages, 4) if p.messages else 0.0,
        "avg_text_length": _avg_len(p), "emoji": p.emoji, "media": dict(p.media.most_common()),
        "longest_silence": {"days": round(gap.total_seconds() / 86400, 1), "from_id": from_id, "to_id": to_id,
                            "from": from_ts.isoformat(sep=" ") if from_ts else None,
                            "to": to_ts.isoformat(sep=" ") if to_ts else None, "until_end": to_id is None and from_id is not None},
        "top_words": p.words.most_common(8), "by_hour": p.hours,
    }


def _pick(people: list[_P], value, keep=lambda p: True, lowest=False):
    """The participant with the highest (or lowest) value; ties go to the name that sorts first."""
    pool = [p for p in people if keep(p) and value(p) is not None]
    if not pool:
        return None
    return min(pool, key=lambda p: ((value(p) if lowest else -value(p)), p.name))


def _award(key: str, title: str, p: _P | None, value, unit: str, ids: list[int | None], rule: str):
    if p is None:
        return None
    return {"award": key, "title": title, "participant_id": p.id, "name": p.name, "value": value, "unit": unit,
            "message_ids": [i for i in ids if i is not None][:3], "rule": rule}


def _awards(per: dict[int, _P]) -> list[dict]:
    people = list(per.values())
    talkers = [p for p in people if p.messages]
    owl = _pick(talkers, lambda p: len(p.night_ids), keep=lambda p: p.night_ids)
    ghost = _pick(talkers, lambda p: p.silence[0].total_seconds(), keep=lambda p: p.silence[1] is not None)
    # Android timestamps are per minute, so medians tie often; the mean breaks the tie.
    fast = [p for p in talkers if len(p.reply_s) >= MIN_SAMPLE]
    speed = min(fast, key=lambda p: (_median(p.reply_s), statistics.fmean(p.reply_s), p.name)) if fast else None
    essay = _pick(talkers, _avg_len, keep=lambda p: len(p.text_lens) >= MIN_SAMPLE)
    hype = _pick(talkers, lambda p: p.emoji, keep=lambda p: p.emoji)
    lurker = _pick(people, lambda p: p.messages, lowest=True) if len(people) > 2 else None
    out = [
        _award("night_owl", "Night Owl", owl, owl and len(owl.night_ids), "messages between 00:00 and 04:00",
               owl.night_ids[-3:] if owl else [], "most messages sent between midnight and 4 AM"),
        _award("ghost", "Ghost", ghost, ghost and round(ghost.silence[0].total_seconds() / 86400, 1), "days silent",
               [ghost.silence[1], ghost.silence[2]] if ghost else [], "longest silence between their messages"),
        _award("speed_replier", "Speed Replier", speed, speed and _median(speed.reply_s), "seconds, median reply",
               [], f"fastest median reply time, ties broken by the mean (at least {MIN_SAMPLE} replies)"),
        _award("essayist", "Essayist", essay, essay and _avg_len(essay), "characters per message",
               [max(essay.text_lens)[1]] if essay else [], f"longest average text message (at least {MIN_SAMPLE})"),
        _award("hype_machine", "Hype Machine", hype, hype and hype.emoji, "emoji",
               [hype.emoji_best[1]] if hype else [], "most emoji sent"),
        _award("lurker", "Lurker", lurker, lurker and lurker.messages, "messages", lurker.ids[:3] if lurker else [],
               "fewest messages"),
    ]
    return [a for a in out if a]


def _couple(agg) -> dict | None:
    pairs: Counter[tuple[int, int]] = Counter()
    for (a, b), n in (agg["replies"] + agg["mentions"]).items():
        pairs[tuple(sorted((a, b)))] += n
    if not pairs:
        return None
    (a, b), n = max(pairs.items(), key=lambda kv: (kv[1], -kv[0][0], -kv[0][1]))
    return {"participant_ids": [a, b], "interactions": n}


def stats(pid: int, chat_id: int | None = None) -> dict | None:
    """Everything countable about one chat (chat_id) or the whole project. None if the chat is not in the project."""
    computed = _compute(pid, chat_id)
    if computed is None:
        return None
    chat, per, rows, agg = computed
    total = sum(p.messages for p in per.values())
    talkers = [p for p in per.values() if p.messages]
    starter = _pick(talkers, lambda p: p.starts)
    talker = _pick(talkers, lambda p: p.messages)
    voice = _pick(talkers, lambda p: p.media["voice"], keep=lambda p: p.media["voice"])
    busiest = max(agg["days"].items(), key=lambda kv: (kv[1], kv[0])) if agg["days"] else None
    couple = _couple(agg)
    if couple:
        couple["names"] = [per[i].name for i in couple["participant_ids"]]
    stamped = [r["ts"] for r in rows]
    ref = lambda p: {"participant_id": p.id, "name": p.name} if p else None  # noqa: E731
    return {
        "scope": {"project_id": pid, "chat_id": chat_id, "chat_title": chat["title"] if chat else None},
        "totals": {"messages": total, "participants": len(per), "active_participants": len(talkers),
                   "conversations": sum(p.starts for p in per.values()),
                   "first": min(stamped) if stamped else None, "last": max(stamped) if stamped else None,
                   "active_days": len(agg["days"]), "media": dict(agg["media"].most_common())},
        "activity": {"by_hour": agg["hours"], "by_weekday": agg["weekdays"],
                     "busiest_day": {"date": busiest[0], "messages": busiest[1]} if busiest else None},
        "highlights": {
            "top_talker": ref(talker) and {**ref(talker), "messages": talker.messages},
            "conversation_starter": ref(starter) and {**ref(starter), "starts": starter.starts},
            "voice_note_king": ref(voice) and {**ref(voice), "voice_notes": voice.media["voice"]},
            "power_couple": couple,
        },
        "top_words": agg["words"].most_common(15),
        "top_emoji": agg["emoji"].most_common(10),
        "participants": sorted((_person(p, total) for p in per.values()), key=lambda d: (-d["messages"], d["name"])),
        "awards": _awards(per),
        "definitions": DEFINITIONS,
    }


def graph(pid: int, chat_id: int | None = None) -> dict | None:
    """Who replies to whom (within REPLY_WINDOW) and who @mentions whom. Edges point from the replier."""
    computed = _compute(pid, chat_id)
    if computed is None:
        return None
    _, per, _, agg = computed
    keys = set(agg["replies"]) | set(agg["mentions"])
    edges = sorted(({"source": a, "target": b, "replies": agg["replies"][(a, b)], "mentions": agg["mentions"][(a, b)],
                     "weight": agg["replies"][(a, b)] + agg["mentions"][(a, b)]} for a, b in keys),
                   key=lambda e: (-e["weight"], e["source"], e["target"]))
    nodes = sorted(({"id": p.id, "name": p.name, "is_me": p.is_me, "messages": p.messages} for p in per.values()),
                   key=lambda n: (-n["messages"], n["name"]))
    return {"nodes": nodes, "edges": edges, "power_couple": _couple(agg),
            "rule": f"a reply is the next message from someone else within {int(REPLY_WINDOW.total_seconds() // 60)} minutes"}
