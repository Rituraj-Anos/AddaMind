"""Media analysis (F2.7): image descriptions, voice transcripts, video summaries and PDF text.

Results are cached by file hash, written to the media row, and added to the message's search text.
Stickers, GIFs and contacts are skipped. ADDAMIND_MEDIA=off leaves files pending (tests, offline).

    python -m backend.chatintel.media <project_id> <chat_id>     process pending and failed files
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from backend.core.config import env_int, env_str

from . import db, retrieval

log = logging.getLogger("addamind.media")

VISION_MODEL = env_str("ADDAMIND_VISION_MODEL", "gemini-3.5-flash-lite")
WHISPER_MODEL = "whisper-large-v3-turbo"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
WORKERS = 3
MAX_INLINE = 20 * 1024 * 1024  # Gemini inline data limit
MAX_WHISPER = 25 * 1024 * 1024  # Groq file limit
CACHE_VERSION = "1"  # bump when prompts change, so old results are redone

IMAGE_PROMPT = ("This image was shared in a WhatsApp chat. In at most two sentences, say what it shows. "
                "If it has readable text (a ticket, receipt, bill, screenshot, sign), copy the important text "
                "exactly after 'Text:'. No preamble.")
VIDEO_PROMPT = ("This video was shared in a WhatsApp chat. In at most two sentences, say what happens and where. "
                "Mention any readable text or clear speech. No preamble.")
AUDIO_PROMPT = ("Transcribe this voice note exactly as spoken. It may be Hinglish (Hindi in Latin letters mixed "
                "with English) or another language: keep the original language and script. Output only the transcript.")


class MediaError(Exception):
    def __init__(self, msg: str, retry: bool = False):
        super().__init__(msg)
        self.retry = retry


class Skip(Exception):
    """Not analysed on purpose (kind not supported, too large)."""


def enabled() -> bool:
    return env_str("ADDAMIND_MEDIA", "on").lower() not in ("off", "0", "false", "no")


class _Limiter:
    """Spaces requests to stay under a provider's per-minute limit, shared by all worker threads."""

    def __init__(self, per_minute: int):
        self.gap = 60.0 / max(per_minute, 1)
        self.next = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            at = max(now, self.next)
            self.next = at + self.gap
        time.sleep(at - now)

    def pause(self, seconds: float) -> None:
        with self.lock:
            self.next = max(self.next, time.monotonic() + seconds)


_GROQ = _Limiter(env_int("GROQ_WHISPER_RPM", 18))
_GEMINI = _Limiter(env_int("GEMINI_MEDIA_RPM", 12))
_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')


def _post(limiter: _Limiter, url: str, **kw) -> dict:
    for attempt in range(4):
        limiter.wait()
        try:
            r = requests.post(url, timeout=(5, 90), **kw)
        except requests.RequestException as e:
            raise MediaError(type(e).__name__, retry=True) from None
        if r.status_code == 429 and attempt < 3:
            m = _RETRY_DELAY.search(r.text)
            wait = float(r.headers.get("retry-after") or (m.group(1) if m else 20))
            limiter.pause(min(wait, 60.0))
            continue
        if not r.ok:
            raise MediaError(f"HTTP {r.status_code}", retry=r.status_code >= 500 or r.status_code == 429)
        try:
            return r.json()
        except ValueError:
            raise MediaError("response was not JSON", retry=True) from None
    raise MediaError("rate limited", retry=True)


def _gemini(data: bytes, mime: str, prompt: str) -> str:
    body = {"contents": [{"parts": [{"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}},
                                    {"text": prompt}]}],
            "generationConfig": {"temperature": 0.2}}
    j = _post(_GEMINI, f"{GEMINI_URL}/{VISION_MODEL}:generateContent",
              headers={"x-goog-api-key": env_str("GEMINI_API_KEY")}, json=body)
    parts = (((j.get("candidates") or [{}])[0].get("content")) or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise MediaError("empty response", retry=True)
    return text


def _whisper(data: bytes, filename: str, prompt: str) -> str:
    j = _post(_GROQ, "https://api.groq.com/openai/v1/audio/transcriptions",
              headers={"Authorization": f"Bearer {env_str('GROQ_API_KEY')}"},
              files={"file": (filename, data)},
              data={"model": WHISPER_MODEL, "response_format": "json", "temperature": "0", "prompt": prompt})
    return (j.get("text") or "").strip()


def _audio_name(path: str) -> str:
    # Groq picks the decoder from the extension and rejects .opus; WhatsApp voice notes are Ogg Opus.
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else "ogg"
    return f"audio.{'ogg' if ext in ('opus', 'oga') else ext}"


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        text = " ".join((p.extract_text() or "") for p in reader.pages[:5])
    except Exception as e:  # noqa: BLE001 - corrupt PDFs raise many types
        raise MediaError(f"unreadable PDF ({type(e).__name__})") from None
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1500] if text else "(no text in this PDF)"


def analyse(kind: str, data: bytes, mime: str | None, path: str, vocabulary: str) -> str:
    """One file -> a short text result. Raises Skip or MediaError."""
    if kind == "image":
        if len(data) > MAX_INLINE:
            raise Skip("image is over 20 MB")
        return _gemini(data, mime or "image/jpeg", IMAGE_PROMPT)
    if kind in ("voice", "audio"):
        if len(data) > MAX_WHISPER:
            raise Skip("audio is over 25 MB")
        try:
            text = _whisper(data, _audio_name(path), vocabulary)
        except MediaError as e:
            log.warning("whisper failed (%s), trying Gemini audio", e)
            if len(data) > MAX_INLINE:
                raise
            text = _gemini(data, "audio/ogg" if path.lower().endswith((".opus", ".ogg")) else (mime or "audio/mpeg"),
                           AUDIO_PROMPT)
        return text or "(no speech)"
    if kind == "video":
        if len(data) > MAX_INLINE:
            raise Skip("video is over 20 MB, not analysed")
        return _gemini(data, mime or "video/mp4", VIDEO_PROMPT)
    if kind == "document":
        if path.lower().endswith(".pdf"):
            return _pdf_text(data)
        raise Skip("only PDF documents are read")
    raise Skip(f"{kind}s are not analysed")


def _vocabulary(con, cid: int) -> str:
    """Whisper prompt: the chat's first names plus common Hinglish words, which fixes most misspellings."""
    names = [r["name"].split()[0] for r in con.execute(
        "SELECT p.name FROM participants p JOIN chat_members cm ON cm.participant_id = p.id "
        "WHERE cm.chat_id = ? AND p.masked = 0 LIMIT 25", (cid,)).fetchall()]
    return ("Hinglish voice note between friends on WhatsApp. Names: " + ", ".join(dict.fromkeys(names)) +
            ". Words: bhai, yaar, ek minute, pakka, acha, theek hai, kya, nahi, haan.")


def _process_one(pid: int, cid: int, row, vocabulary: str) -> tuple[str, str | None, str | None]:
    """-> (status, result, error)."""
    key = f"media:{CACHE_VERSION}:{row['kind']}:{row['sha256']}"
    with db.connect() as con:
        hit = con.execute("SELECT value FROM llm_cache WHERE key = ?", (key,)).fetchone()
    if hit:
        return "done", json.loads(hit["value"]), None
    try:
        data = (db.chat_dir(pid, cid) / row["path"]).read_bytes()
    except OSError:
        return "failed", None, "file is missing on disk"
    for attempt in range(2):  # one retry for transient errors
        try:
            result = analyse(row["kind"], data, row["mime"], row["path"], vocabulary)
            break
        except Skip as e:
            return "skipped", None, str(e)
        except MediaError as e:
            if e.retry and attempt == 0:
                time.sleep(2)
                continue
            return "failed", None, str(e)
    with db.connect() as con:
        con.execute("INSERT OR REPLACE INTO llm_cache(key, value) VALUES (?, ?)", (key, json.dumps(result)))
    return "done", result, None


def _save(row, status: str, result: str | None, error: str | None) -> None:
    with db.connect() as con:
        con.execute("UPDATE media SET status = ?, result = ?, error = ? WHERE id = ?", (status, result, error, row["id"]))
        if result:
            con.execute("UPDATE messages_fts SET text = ? WHERE rowid = ?",
                        (db.media_line(row["kind"], row["text"], result), row["message_id"]))


def process_chat(pid: int, cid: int, on_progress=None, statuses=("pending",), cap: int | None = None) -> dict:
    """Analyse this chat's media in the given statuses, 3 at a time. Never raises for one bad file.
    Returns counts plus the passages that must be rebuilt because their messages gained text."""
    cap = env_int("ADDAMIND_MEDIA_CAP", 500) if cap is None else cap
    with db.connect() as con:
        rows = con.execute(
            f"SELECT md.id, md.kind, md.path, md.mime, md.sha256, md.message_id, m.text, m.passage_id "
            f"FROM media md JOIN messages m ON m.id = md.message_id JOIN chats c ON c.id = md.chat_id "
            f"WHERE md.chat_id = ? AND c.project_id = ? AND md.status IN ({','.join('?' * len(statuses))}) "
            f"ORDER BY md.id", (cid, pid, *statuses)).fetchall()
        vocabulary = _vocabulary(con, cid)
    counts = {"done": 0, "failed": 0, "skipped": 0, "pending": 0}
    if not enabled():
        counts["pending"] = len(rows)
        return counts
    over, rows = rows[cap:], rows[:cap]
    for r in over:
        _save(r, "skipped", None, "over the per-upload processing cap")
    counts["skipped"] += len(over)
    # Forwarded files repeat: analyse each (kind, hash) once, even when copies would run in parallel.
    same: dict[tuple, list] = defaultdict(list)
    for r in rows:
        same[(r["kind"], r["sha256"])].append(r)
    stale, done = set(), 0
    with ThreadPoolExecutor(WORKERS, thread_name_prefix="media") as pool:
        futures = {pool.submit(_process_one, pid, cid, group[0], vocabulary): group for group in same.values()}
        for fut in as_completed(futures):
            group = futures[fut]
            try:
                status, result, error = fut.result()
            except Exception as e:  # noqa: BLE001 - a bug on one file must not stop the rest
                status, result, error = "failed", None, f"internal error ({type(e).__name__})"
            for r in group:
                _save(r, status, result, error)
                counts[status] += 1
                if result and r["passage_id"]:
                    stale.add(r["passage_id"])
            done += len(group)
            if on_progress:
                on_progress(done, len(rows))
    if stale:
        retrieval.refresh_passages(pid, cid, sorted(stale))
    return counts


def main(argv: list[str]) -> None:
    pid, cid = int(argv[0]), int(argv[1])
    t = time.time()
    out = process_chat(pid, cid, lambda d, n: print(f"\r{d}/{n}", end="", flush=True), ("pending", "failed"))
    print(f"\n{out} in {time.time() - t:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1:])
