"""Turn an uploaded WhatsApp export into rows, as a background job with live progress.

Stages run in order. Later tasks append theirs to STAGES (media analysis, index, memory, personas).
Message text never goes to the log: failures log the exception type and the stack only.
"""
from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import re
import shutil
import time
import traceback
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable

from . import db, media, memory, personas, retrieval
from .parser import Message, norm_name, parse_export

log = logging.getLogger("addamind.ingest")

MAX_UPLOAD_BYTES = 300 * 1024 * 1024
MAX_UNZIPPED_BYTES = 1024 * 1024 * 1024
MAX_FILES = 5000
_CHUNK = 1024 * 1024
_MIME = {".opus": "audio/ogg", ".webp": "image/webp", ".m4a": "audio/mp4", ".vcf": "text/vcard"}


@dataclass
class Job:
    id: int
    project_id: int
    filename: str
    path: Path
    chat_id: int | None
    created_chat: bool = False
    new: list[tuple[int, Message]] = field(default_factory=list)  # messages this upload added
    info: dict = field(default_factory=dict)
    _last: float = 0.0

    def progress(self, done: int, total: int) -> None:
        t = time.monotonic()
        if done >= total or t - self._last > 0.3:
            self._last = t
            _update(self.id, done=done, total=total)


def upload_path(pid: int, job_id: int) -> Path:
    return db.project_dir(pid) / "uploads" / f"{int(job_id)}.upload"


def create_job(pid: int, filename: str, chat_id: int | None = None) -> int:
    with db.connect() as con:
        cur = con.execute("INSERT INTO jobs(project_id, chat_id, filename, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                          (pid, chat_id, filename, db.now(), db.now()))
    return cur.lastrowid


def save_upload(src: BinaryIO, pid: int, job_id: int) -> int:
    """Stream the upload to disk, refusing anything over MAX_UPLOAD_BYTES."""
    path = upload_path(pid, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with open(path, "wb") as out:
            while chunk := src.read(_CHUNK):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ValueError(f"the upload is larger than {MAX_UPLOAD_BYTES >> 20} MB")
                out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return size


def _update(job_id: int, **fields) -> None:
    fields["updated_at"] = db.now()
    if "info" in fields:
        fields["info"] = json.dumps(fields["info"])
    cols = ", ".join(f"{k} = ?" for k in fields)  # keys are ours, never user input
    with db.connect() as con:
        con.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))


def fail_job(job_id: int, error: str) -> None:
    _update(job_id, status="failed", error=error)


# ---------------------------------------------------------------- checks and helpers
def check_zip(z: zipfile.ZipFile) -> None:
    infos = z.infolist()
    if len(infos) > MAX_FILES:
        raise ValueError(f"the zip has more than {MAX_FILES} files")
    if sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
        raise ValueError(f"the zip unpacks to more than {MAX_UNZIPPED_BYTES >> 30} GB")
    for i in infos:
        name = i.filename.replace("\\", "/")
        if name.startswith("/") or re.match(r"[A-Za-z]:", name) or ".." in name.split("/"):
            raise ValueError("the zip contains a file path that points outside the export")


def message_hashes(messages: list[Message]) -> list[str]:
    """Stable per-message keys, so a newer export of the same chat only adds what is new.
    Identical messages in the same minute stay distinct through their occurrence number."""
    seen: Counter[str] = Counter()
    out = []
    for m in messages:
        key = "\x1f".join([m.ts.isoformat(), norm_name(m.sender or ""), m.kind, m.text, m.attachment or ""])
        seen[key] += 1
        out.append(hashlib.sha1(f"{key}\x1f{seen[key]}".encode()).hexdigest())
    return out


def _participant(con, pid: int, name: str) -> int:
    key = norm_name(name)
    r = con.execute("SELECT id, merged_into FROM participants WHERE project_id = ? AND norm_name = ?",
                    (pid, key)).fetchone()
    if r:
        return r["merged_into"] or r["id"]
    return con.execute("INSERT INTO participants(project_id, name, norm_name, masked) VALUES (?, ?, ?, ?)",
                       (pid, name, key, int(db.is_phone(name)))).lastrowid


def _safe_name(mid: int, attachment: str) -> str:
    base = PurePosixPath(attachment.replace("\\", "/")).name
    return f"{mid}-" + re.sub(r"[^\w.\-]+", "_", base)[:120]


def _mime(name: str) -> str | None:
    ext = PurePosixPath(name).suffix.lower()
    return _MIME.get(ext) or mimetypes.guess_type(name)[0]


def _copy(z: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path, used: int) -> tuple[int, str]:
    """Copy one member, counting real bytes (zip headers can lie about sizes)."""
    h, size = hashlib.sha256(), 0
    try:
        with z.open(info) as src, open(target, "wb") as out:
            while chunk := src.read(_CHUNK):
                size += len(chunk)
                if used + size > MAX_UNZIPPED_BYTES:
                    raise ValueError(f"the zip unpacks to more than {MAX_UNZIPPED_BYTES >> 30} GB")
                h.update(chunk)
                out.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return size, h.hexdigest()


# ---------------------------------------------------------------- stages
def stage_parse(job: Job) -> None:
    """Parse, store participants and new messages, then save the media files they reference."""
    pid = job.project_id
    with open(job.path, "rb") as f:
        if zipfile.is_zipfile(f):
            with zipfile.ZipFile(f) as z:
                check_zip(z)
        f.seek(0)
        chat, _ = parse_export(f, job.filename)
    hashes = message_hashes(chat.messages)
    job.progress(0, len(chat.messages))

    with db.connect() as con:
        cid = job.chat_id or _matching_chat(con, pid, chat.title, chat.kind)
        if cid is None:
            cid = con.execute("INSERT INTO chats(project_id, title, kind, source_format, created_at) "
                              "VALUES (?, ?, ?, ?, ?)", (pid, chat.title, chat.kind, chat.source_format, db.now())).lastrowid
            created = True
        else:
            con.execute("UPDATE chats SET status = 'processing' WHERE id = ?", (cid,))
            created = False
        con.execute("UPDATE jobs SET chat_id = ? WHERE id = ?", (cid, job.id))
        ids = {name: _participant(con, pid, name) for name in chat.participants}
        con.executemany("INSERT OR IGNORE INTO chat_members VALUES (?, ?)", [(cid, i) for i in set(ids.values())])
        if chat.me_guess and not con.execute("SELECT 1 FROM participants WHERE project_id = ? AND is_me = 1",
                                             (pid,)).fetchone():
            con.execute("UPDATE participants SET is_me = 1 WHERE id = ?", (ids[chat.me_guess],))
        new = []
        for m, h in zip(chat.messages, hashes):
            cur = con.execute("INSERT OR IGNORE INTO messages(chat_id, participant_id, ts, kind, text, attachment, "
                              "edited, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              (cid, ids.get(m.sender), m.ts.isoformat(sep=" "), m.kind, m.text, m.attachment,
                               int(m.edited), h))
            if cur.rowcount:
                new.append((cur.lastrowid, m))
                con.executemany("INSERT OR IGNORE INTO message_mentions VALUES (?, ?)",
                                [(cur.lastrowid, ids[p]) for p in m.mentions if p in ids])
    job.chat_id, job.created_chat, job.new = cid, created, new
    job.progress(len(chat.messages), len(chat.messages))
    job.info.update(title=chat.title, kind=chat.kind, created=created, messages=len(chat.messages),
                    inserted=len(new), skipped=len(chat.messages) - len(new),
                    months=sorted({m.ts.strftime("%Y-%m") for _, m in new}),
                    first_new_id=new[0][0] if new else None)  # catch-up's "since the latest upload"
    _save_media(job)


def _matching_chat(con, pid: int, title: str, kind: str) -> int | None:
    # shortcut: a re-upload is matched by title and kind; two different groups with one name would merge.
    r = con.execute("SELECT id FROM chats WHERE project_id = ? AND kind = ? AND title = ? COLLATE NOCASE "
                    "ORDER BY id LIMIT 1", (pid, kind, title)).fetchone()
    return r["id"] if r else None


def _save_media(job: Job) -> None:
    """Extract every attachment of this chat that has no saved file yet (so a zip after a .txt fills in media)."""
    with db.connect() as con:
        todo = con.execute("SELECT m.id, m.kind, m.attachment FROM messages m LEFT JOIN media md ON md.message_id = m.id "
                           "WHERE m.chat_id = ? AND m.attachment IS NOT NULL AND md.id IS NULL", (job.chat_id,)).fetchall()
    saved = []
    with open(job.path, "rb") as f:
        if todo and zipfile.is_zipfile(f):
            f.seek(0)
            with zipfile.ZipFile(f) as z:
                members = {PurePosixPath(i.filename.replace("\\", "/")).name: i
                           for i in z.infolist() if not i.is_dir()}
                dest = db.chat_dir(job.project_id, job.chat_id)
                dest.mkdir(parents=True, exist_ok=True)
                base, used = dest.resolve(), 0
                for n, r in enumerate(todo, 1):
                    info = members.get(r["attachment"])
                    if info:
                        name = _safe_name(r["id"], r["attachment"])
                        target = base / name
                        if target.resolve().parent != base:
                            raise ValueError("unsafe media file name")
                        size, sha = _copy(z, info, target, used)
                        used += size
                        saved.append((job.chat_id, r["id"], r["kind"], name, _mime(name), size, sha))
                    job.progress(n, len(todo))
    with db.connect() as con:
        con.executemany("INSERT INTO media(chat_id, message_id, kind, path, mime, size, sha256) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)", saved)
    job.info.update(media_saved=len(saved), media_missing=len(todo) - len(saved))


def stage_media(job: Job) -> None:
    """Describe images and videos, transcribe voice notes, read PDFs. Runs before indexing so passages
    already carry the results."""
    counts = media.process_chat(job.project_id, job.chat_id, job.progress)
    job.info.update({f"media_{k}": v for k, v in counts.items()})


def stage_index(job: Job) -> None:
    """Passages for the new messages, with embeddings (keyword search still works if those fail)."""
    job.info.update(retrieval.build_passages(job.project_id, job.chat_id, job.progress))


def stage_memory(job: Job) -> None:
    """Monthly summaries for months this upload touched (all of them for a new chat), then chat memory."""
    if not memory.enabled():
        job.info["memory"] = "off"
        return
    job.info.update(memory.build_memory(job.project_id, job.chat_id, job.info.get("months"), job.progress))


def stage_personas(job: Job) -> None:
    if not memory.enabled() or not job.new:
        return
    job.info.update(personas.build_top(job.project_id, job.chat_id, on_progress=job.progress))


STAGES: list[tuple[str, Callable[[Job], None]]] = [("parse", stage_parse), ("media", stage_media),
                                                   ("index", stage_index), ("memory", stage_memory),
                                                   ("personas", stage_personas)]


def run_job(pid: int, job_id: int) -> None:
    """Run every stage for one upload. Safe to call in a background thread."""
    path = upload_path(pid, job_id)
    job = None
    try:
        with db.connect() as con:
            r = con.execute("SELECT * FROM jobs WHERE id = ? AND project_id = ?", (job_id, pid)).fetchone()
        if not r:
            return
        job = Job(job_id, pid, r["filename"], path, r["chat_id"])
        for name, fn in STAGES:
            _update(job_id, status="running", stage=name, done=0, total=0)
            fn(job)
        with db.connect() as con:
            con.execute("UPDATE chats SET status = 'ready' WHERE id = ?", (job.chat_id,))
        _update(job_id, status="done", stage="done", error=None, info=job.info)
    except Exception as e:  # noqa: BLE001 - every failure must end the job, not the server
        msg = str(e) if isinstance(e, ValueError) else f"processing failed ({type(e).__name__})"
        log.error("job %s failed: %s\n%s", job_id, type(e).__name__, "".join(traceback.format_tb(e.__traceback__)))
        try:
            _update(job_id, status="failed", error=msg, info=job.info if job else {})
            if job and job.chat_id:
                with db.connect() as con:
                    con.execute("UPDATE chats SET status = ? WHERE id = ?",
                                ("failed" if job.created_chat else "ready", job.chat_id))
        except Exception:  # noqa: BLE001 - the project was deleted while the job ran
            pass
    finally:
        path.unlink(missing_ok=True)
        # The chat or project may have been deleted while this job wrote files: remove what it left.
        if db.get_project(pid) is None:
            shutil.rmtree(db.project_dir(pid), ignore_errors=True)
        elif job and job.chat_id and db.get_chat(pid, job.chat_id) is None:
            shutil.rmtree(db.chat_dir(pid, job.chat_id), ignore_errors=True)
