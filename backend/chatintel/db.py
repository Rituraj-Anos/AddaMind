"""SQLite storage for AddaMind (`.cache/addamind.db`, WAL). Every read and write is scoped by project_id.

Media files live under `.cache/projects/<project>/<chat>/`. Set ADDAMIND_DATA to move both (tests do).
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.core.config import CACHE_DIR, env_str

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS participants(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects ON DELETE CASCADE,
  name TEXT NOT NULL, norm_name TEXT NOT NULL, is_me INTEGER NOT NULL DEFAULT 0,
  roast_opt_out INTEGER NOT NULL DEFAULT 0, masked INTEGER NOT NULL DEFAULT 0,
  merged_into INTEGER REFERENCES participants ON DELETE CASCADE,
  UNIQUE(project_id, norm_name));
CREATE TABLE IF NOT EXISTS chats(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects ON DELETE CASCADE,
  title TEXT NOT NULL, kind TEXT NOT NULL, source_format TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'processing', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS chats_project ON chats(project_id);
CREATE TABLE IF NOT EXISTS chat_members(
  chat_id INTEGER NOT NULL REFERENCES chats ON DELETE CASCADE,
  participant_id INTEGER NOT NULL REFERENCES participants ON DELETE CASCADE,
  PRIMARY KEY(chat_id, participant_id)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL REFERENCES chats ON DELETE CASCADE,
  participant_id INTEGER REFERENCES participants ON DELETE SET NULL,
  ts TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, attachment TEXT,
  edited INTEGER NOT NULL DEFAULT 0, hash TEXT NOT NULL,
  passage_id INTEGER REFERENCES passages ON DELETE SET NULL, UNIQUE(chat_id, hash));
CREATE INDEX IF NOT EXISTS messages_chat_ts ON messages(chat_id, ts, id);
CREATE INDEX IF NOT EXISTS messages_participant ON messages(participant_id);
CREATE INDEX IF NOT EXISTS messages_passage ON messages(passage_id);
CREATE TABLE IF NOT EXISTS message_mentions(
  message_id INTEGER NOT NULL REFERENCES messages ON DELETE CASCADE,
  participant_id INTEGER NOT NULL REFERENCES participants ON DELETE CASCADE,
  PRIMARY KEY(message_id, participant_id)) WITHOUT ROWID;
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(text, tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text); END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  DELETE FROM messages_fts WHERE rowid = old.id; END;
CREATE TABLE IF NOT EXISTS media(
  id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL REFERENCES chats ON DELETE CASCADE,
  message_id INTEGER NOT NULL REFERENCES messages ON DELETE CASCADE,
  kind TEXT NOT NULL, path TEXT NOT NULL, mime TEXT, size INTEGER, sha256 TEXT,
  status TEXT NOT NULL DEFAULT 'pending', result TEXT, error TEXT);
CREATE INDEX IF NOT EXISTS media_message ON media(message_id);
CREATE INDEX IF NOT EXISTS media_chat ON media(chat_id, status);
CREATE TABLE IF NOT EXISTS passages(
  id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL REFERENCES chats ON DELETE CASCADE,
  first_msg INTEGER NOT NULL, last_msg INTEGER NOT NULL, first_ts TEXT NOT NULL, last_ts TEXT NOT NULL,
  text TEXT NOT NULL, model TEXT, embedding BLOB);
CREATE INDEX IF NOT EXISTS passages_chat ON passages(chat_id);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(text, tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS passages_ai AFTER INSERT ON passages BEGIN
  INSERT INTO passages_fts(rowid, text) VALUES (new.id, new.text); END;
CREATE TRIGGER IF NOT EXISTS passages_ad AFTER DELETE ON passages BEGIN
  DELETE FROM passages_fts WHERE rowid = old.id; END;
CREATE TABLE IF NOT EXISTS month_summaries(
  chat_id INTEGER NOT NULL REFERENCES chats ON DELETE CASCADE, month TEXT NOT NULL, json TEXT NOT NULL,
  PRIMARY KEY(chat_id, month));
CREATE TABLE IF NOT EXISTS chat_memory(
  chat_id INTEGER PRIMARY KEY REFERENCES chats ON DELETE CASCADE, json TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS personas(
  id INTEGER PRIMARY KEY, participant_id INTEGER NOT NULL REFERENCES participants ON DELETE CASCADE,
  chat_id INTEGER REFERENCES chats ON DELETE CASCADE, json TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS personas_key ON personas(participant_id, IFNULL(chat_id, 0));
CREATE TABLE IF NOT EXISTS threads(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects ON DELETE CASCADE,
  agent TEXT NOT NULL, scope_type TEXT NOT NULL, scope_id INTEGER, title TEXT,
  messages TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects ON DELETE CASCADE,
  chat_id INTEGER REFERENCES chats ON DELETE CASCADE, filename TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued', stage TEXT NOT NULL DEFAULT 'queued',
  done INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0, error TEXT, info TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS llm_cache(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS read_marks(
  chat_id INTEGER NOT NULL REFERENCES chats ON DELETE CASCADE, owner TEXT NOT NULL DEFAULT '',
  message_id INTEGER NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(chat_id, owner)) WITHOUT ROWID;
"""

_ready: set[str] = set()
_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def data_dir() -> Path:
    return Path(env_str("ADDAMIND_DATA") or CACHE_DIR)


def project_dir(pid: int) -> Path:
    return data_dir() / "projects" / str(int(pid))


def chat_dir(pid: int, cid: int) -> Path:
    return project_dir(pid) / str(int(cid))


@contextmanager
def connect():
    """One connection per unit of work; commits on success, rolls back on error."""
    path = data_dir() / "addamind.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        if str(path) not in _ready:
            with _lock:
                if str(path) not in _ready:
                    con.execute("PRAGMA journal_mode = WAL")
                    con.executescript(SCHEMA)
                    # owner: the visitor id that created it (NULL = shared, like the demo); added to older files too
                    for table in ("projects", "threads"):
                        if "owner" not in {r[1] for r in con.execute(f"PRAGMA table_info({table})")}:
                            con.execute(f"ALTER TABLE {table} ADD COLUMN owner TEXT")
                    _ready.add(str(path))
        with con:
            yield con
    finally:
        con.close()


def load_seed() -> bool:
    """First boot on an empty disk (a fresh Render deploy): copy the synthetic demo project from /seed.
    Does nothing if a database already exists, so local data is never overwritten."""
    seed = Path(__file__).resolve().parents[2] / "seed"
    if (data_dir() / "addamind.db").exists() or not (seed / "addamind.db").exists():
        return False
    shutil.copytree(seed, data_dir(), dirs_exist_ok=True)
    return True


def recover_jobs() -> int:
    """Jobs run in server threads and die with the server. Call once at API startup (not from CLIs,
    which would mark a running server's jobs failed)."""
    with connect() as con:
        n = con.execute("UPDATE jobs SET status = 'failed', error = 'interrupted by a server restart' "
                        "WHERE status IN ('queued', 'running')").rowcount
        con.execute("UPDATE chats SET status = 'failed' WHERE status = 'processing'")
    return n


# ---------------------------------------------------------------- display helpers
_PHONE = re.compile(r"^\+?[\d\s\-()]{7,}$")


def is_phone(name: str) -> bool:
    return bool(_PHONE.match(name.strip()))


def mask(name: str) -> str:
    """'+91 98311 45678' -> '+91 ••••• ••678'. Keeps the country code and the last three digits."""
    cc, rest = name.split(" ", 1) if name.startswith("+") and " " in name else ("", name)
    return f"{cc} {re.sub(r'\d(?=(?:\D*\d){3})', '•', rest)}".strip()


def shown_name(name: str | None, masked) -> str | None:
    return mask(name) if name and masked else name


MEDIA_LABEL = {"image": "photo", "voice": "voice note", "audio": "audio", "video": "video", "document": "document",
               "sticker": "sticker", "gif": "GIF", "contact": "contact card", "media_omitted": "media not exported"}


# Personal data inside message text, hidden before anything reaches a model or the UI. The database keeps the
# original so deleting a project still removes it.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*\w")
_UPI = re.compile(r"(?<![\w@.])[\w.-]{2,}@[a-z]{2,}(?![\w.@])", re.I)
_SECRET = re.compile(r"(?i)\b(otp|pin|cvv|code|password|passcode|pwd)\b(\W{0,4}(?:is\W{1,3})?)\d{4,8}\b")
_LONG_NUM = re.compile(r"\+?\d[\d \-]{8,}\d")
_DATE = re.compile(r"\d{1,4}-\d{1,2}-\d{1,4}")


def _num(m: re.Match) -> str:
    s = m.group()
    if sum(c.isdigit() for c in s) < 10 or _DATE.match(s):  # short numbers and dates are not personal
        return s
    return re.sub(r"\d(?=(?:\D*\d){3})", "•", s)


def redact(text: str | None) -> str | None:
    """Mask phone, card and account numbers (last 3 digits kept), and hide emails, UPI IDs and OTPs."""
    if not text:
        return text
    text = _EMAIL.sub("[email]", text)
    text = _UPI.sub("[upi id]", text)
    text = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}[code]", text)
    return _LONG_NUM.sub(_num, text)


def media_line(kind: str, text: str | None, result: str | None = None) -> str:
    """Message text with its media, as indexed and shown to agents: 'caption [voice note] "transcript"'."""
    text, result = redact(text), redact(result)
    label = MEDIA_LABEL.get(kind)
    if not label:
        return text or ""
    tail = f'[{label}] "{result}"' if result else f"[{label}]"
    return f"{text} {tail}" if text else tail


# ---------------------------------------------------------------- projects
def create_project(name: str, owner: str | None = None) -> dict:
    with connect() as con:
        cur = con.execute("INSERT INTO projects(name, created_at, owner) VALUES (?, ?, ?)", (name, now(), owner))
    return get_project(cur.lastrowid)


def list_projects() -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT p.*, (SELECT COUNT(*) FROM chats WHERE project_id = p.id) AS chat_count "
                           "FROM projects p ORDER BY p.id DESC").fetchall()
    return [dict(r) for r in rows]


def get_project(pid: int) -> dict | None:
    with connect() as con:
        r = con.execute("SELECT p.*, (SELECT COUNT(*) FROM chats WHERE project_id = p.id) AS chat_count "
                        "FROM projects p WHERE id = ?", (pid,)).fetchone()
    return dict(r) if r else None


def rename_project(pid: int, name: str) -> dict | None:
    with connect() as con:
        con.execute("UPDATE projects SET name = ? WHERE id = ?", (name, pid))
    return get_project(pid)


def _remove_dir(path: Path) -> bool:
    shutil.rmtree(path, ignore_errors=True)
    return not path.exists()


def delete_project(pid: int) -> dict | None:
    with connect() as con:
        if not con.execute("DELETE FROM projects WHERE id = ?", (pid,)).rowcount:
            return None
    return {"deleted": pid, "files_removed": _remove_dir(project_dir(pid))}


def delete_expired(hours: float) -> list[int]:
    """Delete visitor-owned projects older than `hours` (rows and files). Shared projects are kept."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    with connect() as con:
        ids = [r[0] for r in con.execute("SELECT id FROM projects WHERE owner IS NOT NULL AND created_at < ?", (cutoff,))]
    return [pid for pid in ids if delete_project(pid)]


# ---------------------------------------------------------------- chats
_CHAT_SELECT = """
SELECT c.*,
  (SELECT COUNT(*) FROM messages WHERE chat_id = c.id) AS message_count,
  (SELECT COUNT(*) FROM chat_members WHERE chat_id = c.id) AS member_count,
  (SELECT COUNT(*) FROM media WHERE chat_id = c.id) AS media_count,
  (SELECT MIN(ts) FROM messages WHERE chat_id = c.id) AS first_ts,
  (SELECT MAX(ts) FROM messages WHERE chat_id = c.id) AS last_ts
FROM chats c WHERE c.project_id = ?"""


def list_chats(pid: int) -> list[dict]:
    with connect() as con:
        return [dict(r) for r in con.execute(_CHAT_SELECT + " ORDER BY c.id", (pid,)).fetchall()]


def get_chat(pid: int, cid: int) -> dict | None:
    with connect() as con:
        r = con.execute(_CHAT_SELECT + " AND c.id = ?", (pid, cid)).fetchone()
    return dict(r) if r else None


def delete_chat(pid: int, cid: int) -> dict | None:
    with connect() as con:
        if not con.execute("DELETE FROM chats WHERE id = ? AND project_id = ?", (cid, pid)).rowcount:
            return None
        con.execute("DELETE FROM threads WHERE project_id = ? AND scope_type = 'chat' AND scope_id = ?", (pid, cid))
    return {"deleted": cid, "files_removed": _remove_dir(chat_dir(pid, cid))}


# ---------------------------------------------------------------- messages
MSG_SELECT = """
SELECT m.id, m.chat_id, m.participant_id, m.ts, m.kind, m.text, m.edited, p.name AS sender, p.masked,
       md.id AS media_id, md.status AS media_status, md.result AS media_result
FROM messages m JOIN chats c ON c.id = m.chat_id AND c.project_id = ?
LEFT JOIN participants p ON p.id = m.participant_id
LEFT JOIN media md ON md.message_id = m.id"""


def message_json(r) -> dict:
    media = ({"id": r["media_id"], "status": r["media_status"], "result": redact(r["media_result"])}
             if r["media_id"] else None)
    return {"id": r["id"], "chat_id": r["chat_id"], "ts": r["ts"], "participant_id": r["participant_id"],
            "sender": shown_name(r["sender"], r["masked"]), "kind": r["kind"], "text": redact(r["text"]),
            "edited": bool(r["edited"]), "media": media}


def messages_window(pid: int, cid: int, around: int | None = None, before: int | None = None,
                    limit: int = 50) -> list[dict] | None:
    """Messages of one chat in time order: centred on `around`, or the latest ones before `before`.
    Returns None when the chat (or the anchor message) is not in this project."""
    with connect() as con:
        if not con.execute("SELECT 1 FROM chats WHERE id = ? AND project_id = ?", (cid, pid)).fetchone():
            return None
        anchor_id = around if around is not None else before
        anchor = None
        if anchor_id is not None:
            anchor = con.execute("SELECT ts, id FROM messages WHERE id = ? AND chat_id = ?", (anchor_id, cid)).fetchone()
            if not anchor:
                return None
        q = MSG_SELECT + " WHERE m.chat_id = ?"
        if anchor is None:
            rows = con.execute(q + " ORDER BY m.ts DESC, m.id DESC LIMIT ?", (pid, cid, limit)).fetchall()[::-1]
        elif around is None:
            rows = con.execute(q + " AND (m.ts, m.id) < (?, ?) ORDER BY m.ts DESC, m.id DESC LIMIT ?",
                               (pid, cid, anchor["ts"], anchor["id"], limit)).fetchall()[::-1]
        else:
            half = max(limit // 2, 0)
            head = con.execute(q + " AND (m.ts, m.id) < (?, ?) ORDER BY m.ts DESC, m.id DESC LIMIT ?",
                               (pid, cid, anchor["ts"], anchor["id"], half)).fetchall()[::-1]
            tail = con.execute(q + " AND (m.ts, m.id) >= (?, ?) ORDER BY m.ts, m.id LIMIT ?",
                               (pid, cid, anchor["ts"], anchor["id"], max(limit - half, 1))).fetchall()
            rows = head + tail
    return [message_json(r) for r in rows]


def get_message(pid: int, mid: int, context: int = 5) -> dict | None:
    with connect() as con:
        r = con.execute("SELECT m.chat_id FROM messages m JOIN chats c ON c.id = m.chat_id "
                        "WHERE m.id = ? AND c.project_id = ?", (mid, pid)).fetchone()
    if not r:
        return None
    rows = messages_window(pid, r["chat_id"], around=mid, limit=2 * context + 1) or []
    i = next(i for i, m in enumerate(rows) if m["id"] == mid)
    return {"message": rows[i], "before": rows[:i], "after": rows[i + 1:]}


def get_media(pid: int, media_id: int) -> tuple[dict, Path] | None:
    with connect() as con:
        r = con.execute("SELECT md.* FROM media md JOIN chats c ON c.id = md.chat_id "
                        "WHERE md.id = ? AND c.project_id = ?", (media_id, pid)).fetchone()
    if not r or not r["path"]:
        return None
    base = chat_dir(pid, r["chat_id"]).resolve()
    path = (base / r["path"]).resolve()
    if path.parent != base or not path.is_file():
        return None
    return dict(r), path


# ---------------------------------------------------------------- participants
def list_participants(pid: int) -> list[dict]:
    with connect() as con:
        rows = con.execute("""
            SELECT p.id, p.name, p.is_me, p.roast_opt_out, p.masked,
              (SELECT COUNT(*) FROM messages WHERE participant_id = p.id) AS message_count,
              (SELECT group_concat(chat_id) FROM chat_members WHERE participant_id = p.id) AS chat_ids
            FROM participants p WHERE p.project_id = ? AND p.merged_into IS NULL
            ORDER BY message_count DESC, p.name""", (pid,)).fetchall()
    return [{"id": r["id"], "name": shown_name(r["name"], r["masked"]), "is_me": bool(r["is_me"]),
             "roast_opt_out": bool(r["roast_opt_out"]), "masked": bool(r["masked"]),
             "message_count": r["message_count"],
             "chat_ids": sorted(int(c) for c in (r["chat_ids"] or "").split(",") if c)} for r in rows]


def _live_participant(con, pid: int, part_id: int):
    return con.execute("SELECT * FROM participants WHERE id = ? AND project_id = ? AND merged_into IS NULL",
                       (part_id, pid)).fetchone()


def update_participant(pid: int, part_id: int, is_me: bool | None = None, roast_opt_out: bool | None = None) -> bool:
    with connect() as con:
        if not _live_participant(con, pid, part_id):
            return False
        if is_me:  # only one "me" per project
            con.execute("UPDATE participants SET is_me = (id = ?) WHERE project_id = ?", (part_id, pid))
        elif is_me is False:
            con.execute("UPDATE participants SET is_me = 0 WHERE id = ?", (part_id,))
        if roast_opt_out is not None:
            con.execute("UPDATE participants SET roast_opt_out = ? WHERE id = ?", (int(roast_opt_out), part_id))
    return True


def merge_participants(pid: int, src: int, into: int) -> bool:
    """Fold `src` into `into`. `src` stays as an alias so later uploads under that name land on `into`."""
    if src == into:
        return False
    with connect() as con:
        a, b = _live_participant(con, pid, src), _live_participant(con, pid, into)
        if not a or not b:
            return False
        con.execute("UPDATE messages SET participant_id = ? WHERE participant_id = ?", (into, src))
        con.execute("INSERT OR IGNORE INTO chat_members SELECT chat_id, ? FROM chat_members WHERE participant_id = ?",
                    (into, src))
        con.execute("DELETE FROM chat_members WHERE participant_id = ?", (src,))
        con.execute("UPDATE OR IGNORE message_mentions SET participant_id = ? WHERE participant_id = ?", (into, src))
        con.execute("DELETE FROM message_mentions WHERE participant_id = ?", (src,))
        con.execute("DELETE FROM personas WHERE participant_id IN (?, ?)", (src, into))  # stale now
        con.execute("UPDATE participants SET is_me = ?, roast_opt_out = ? WHERE id = ?",
                    (a["is_me"] or b["is_me"], a["roast_opt_out"] or b["roast_opt_out"], into))
        con.execute("UPDATE participants SET merged_into = ?, is_me = 0 WHERE id = ? OR merged_into = ?",
                    (into, src, src))
    return True


# ---------------------------------------------------------------- agent threads
def create_thread(pid: int, agent: str, scope_type: str, scope_id: int | None, title: str, owner: str | None = None) -> int:
    with connect() as con:
        return con.execute("INSERT INTO threads(project_id, agent, scope_type, scope_id, title, created_at, updated_at, owner) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (pid, agent, scope_type, scope_id, title[:80], now(), now(), owner)).lastrowid


def get_thread(pid: int, tid: int) -> dict | None:
    with connect() as con:
        r = con.execute("SELECT * FROM threads WHERE id = ? AND project_id = ?", (tid, pid)).fetchone()
    return {**dict(r), "messages": json.loads(r["messages"])} if r else None


def append_thread(pid: int, tid: int, messages: list[dict]) -> None:
    with connect() as con:
        r = con.execute("SELECT messages FROM threads WHERE id = ? AND project_id = ?", (tid, pid)).fetchone()
        if r:
            con.execute("UPDATE threads SET messages = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(json.loads(r["messages"]) + messages, ensure_ascii=False), now(), tid))


def list_threads(pid: int, agent: str | None = None, scope_type: str | None = None, scope_id: int | None = None,
                 visitor: str | None = None) -> list[dict]:
    """Threads in this project that are shared (no owner) or belong to `visitor`."""
    sql, args = "SELECT id, agent, scope_type, scope_id, title, created_at, updated_at FROM threads " \
                "WHERE project_id = ? AND messages != '[]' AND (owner IS NULL OR owner = ?)", [pid, visitor]
    for col, v in (("agent", agent), ("scope_type", scope_type), ("scope_id", scope_id)):
        if v is not None:
            sql += f" AND {col} = ?"
            args.append(v)
    with connect() as con:
        return [dict(r) for r in con.execute(sql + " ORDER BY updated_at DESC, id DESC", args).fetchall()]


def delete_thread(pid: int, tid: int) -> bool:
    with connect() as con:
        return bool(con.execute("DELETE FROM threads WHERE id = ? AND project_id = ?", (tid, pid)).rowcount)


# ---------------------------------------------------------------- jobs
def job_json(r) -> dict:
    d = dict(r)
    d["info"] = json.loads(d["info"]) if d.get("info") else {}
    d.pop("project_id", None)
    return d


def get_job(pid: int, job_id: int) -> dict | None:
    with connect() as con:
        r = con.execute("SELECT * FROM jobs WHERE id = ? AND project_id = ?", (job_id, pid)).fetchone()
    return job_json(r) if r else None


def list_jobs(pid: int, limit: int = 20) -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT * FROM jobs WHERE project_id = ? ORDER BY id DESC LIMIT ?", (pid, limit)).fetchall()
    return [job_json(r) for r in rows]
