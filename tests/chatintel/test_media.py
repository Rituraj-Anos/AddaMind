import io
import zipfile

import pytest

from backend.chatintel import db, ingest, media, retrieval
from backend.chatintel.retrieval import Scope

CHAT = """01/03/25, 9:00 pm - Priya Sen: IMG-20250301-WA0001.jpg (file attached)
tickets book ho gaye
01/03/25, 9:01 pm - Rohan Das: PTT-20250301-WA0002.opus (file attached)
01/03/25, 9:02 pm - Kabir Malhotra: IMG-20250301-WA0003.jpg (file attached)
01/03/25, 9:03 pm - Arjun Mehta: STK-20250301-WA0004.webp (file attached)
01/03/25, 9:04 pm - Arjun Mehta: VID-20250301-WA0005.mp4 (file attached)
01/03/25, 9:05 pm - Sayan Mukherjee: IMG-20250301-WA0006.jpg (file attached)
"""
FILES = {"IMG-20250301-WA0001.jpg": b"ticket-image", "PTT-20250301-WA0002.opus": b"OggS-voice",
         "IMG-20250301-WA0003.jpg": b"corrupt", "STK-20250301-WA0004.webp": b"sticker",
         "VID-20250301-WA0005.mp4": b"video", "IMG-20250301-WA0006.jpg": b"ticket-image"}  # same bytes as 0001


def make_zip(text, files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("WhatsApp Chat with College Friends.txt", text)
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


@pytest.fixture()
def calls(monkeypatch):
    monkeypatch.setenv("ADDAMIND_MEDIA", "on")
    log = []

    def gemini(data, mime, prompt):
        log.append(("gemini", mime, data))
        if data == b"corrupt":
            raise media.MediaError("HTTP 400")
        if data == b"video":
            return "Friends dancing on Baga beach at sunset"
        return "An IndiGo boarding pass. Text: 6E-2134 CCU to GOI"

    def whisper(data, filename, prompt):
        log.append(("whisper", filename, prompt))
        return "ek minute, Abhishek ne tickets bhool gaye"

    monkeypatch.setattr(media, "_gemini", gemini)
    monkeypatch.setattr(media, "_whisper", whisper)
    return log


def load(pid, data, name="WhatsApp Chat with College Friends.zip"):
    job_id = ingest.create_job(pid, name)
    ingest.save_upload(io.BytesIO(data), pid, job_id)
    ingest.run_job(pid, job_id)
    return db.get_job(pid, job_id)


def statuses(pid, cid):
    return [m["media"]["status"] for m in db.messages_window(pid, cid) if m["media"]]


def test_media_results_failures_and_skips(calls):
    pid = db.create_project("Suman")["id"]
    job = load(pid, make_zip(CHAT, FILES))
    assert job["status"] == "done"  # one corrupt file does not fail the upload
    info = job["info"]
    assert (info["media_done"], info["media_failed"], info["media_skipped"]) == (4, 1, 1)
    rows = {m["id"]: m for m in db.messages_window(pid, job["chat_id"])}
    by_kind = {}
    for m in rows.values():
        by_kind.setdefault(m["kind"], []).append(m["media"])
    assert by_kind["voice"][0]["result"] == "ek minute, Abhishek ne tickets bhool gaye"
    assert by_kind["sticker"][0]["status"] == "skipped"
    assert sorted(x["status"] for x in by_kind["image"]) == ["done", "done", "failed"]
    assert by_kind["video"][0]["result"].startswith("Friends dancing")
    # Two images share bytes, so they are analysed once (cached by hash). A 400 is final: no retry.
    assert sum(1 for c in calls if c[0] == "gemini" and c[2] == b"ticket-image") == 1
    assert sum(1 for c in calls if c[2] == b"corrupt") == 1
    whisper = next(c for c in calls if c[0] == "whisper")
    assert whisper[1] == "audio.ogg" and "Rohan" in whisper[2]  # .opus renamed, names in the vocabulary


def test_search_finds_words_spoken_and_shown(calls):
    pid = db.create_project("Suman")["id"]
    load(pid, make_zip(CHAT, FILES))
    voice = retrieval.search(Scope(pid), "bhool gaye")["results"][0]
    assert voice["kind"] == "voice" and voice["sender"] == "Rohan Das"
    assert '[voice note] "ek minute' in voice["context"]
    pnr = retrieval.search(Scope(pid), "6E-2134")["results"]
    assert pnr and pnr[0]["kind"] == "image"


def test_transient_errors_retry_once_then_fall_back(calls, monkeypatch):
    attempts = []

    def flaky_whisper(data, filename, prompt):
        attempts.append(1)
        raise media.MediaError("HTTP 503", retry=True)

    monkeypatch.setattr(media, "_whisper", flaky_whisper)
    monkeypatch.setattr(media.time, "sleep", lambda s: None)
    pid = db.create_project("Suman")["id"]
    job = load(pid, make_zip(CHAT, FILES))
    voice = next(m for m in db.messages_window(pid, job["chat_id"]) if m["kind"] == "voice")["media"]
    # Whisper failed, Gemini audio answered (the fake returns the image text for any other bytes).
    assert voice["status"] == "done" and len(attempts) == 1
    assert any(c[0] == "gemini" and c[1] == "audio/ogg" for c in calls)


def test_media_omitted_export_and_offline_mode(monkeypatch):
    pid = db.create_project("Suman")["id"]
    omitted = "01/03/25, 9:00 pm - Priya Sen: <Media omitted>\n01/03/25, 9:01 pm - Rohan Das: haha\n"
    job = load(pid, omitted.encode(), "WhatsApp Chat with College Friends.txt")
    assert job["status"] == "done" and job["info"]["media_saved"] == 0 and job["info"]["media_done"] == 0
    job = load(pid, make_zip(CHAT, FILES), "WhatsApp Chat with Other.zip")  # ADDAMIND_MEDIA=off from conftest
    assert job["status"] == "done" and job["info"]["media_pending"] == 6
    assert set(statuses(pid, job["chat_id"])) == {"pending"}


def test_cap_marks_the_rest_skipped(calls, monkeypatch):
    monkeypatch.setenv("ADDAMIND_MEDIA_CAP", "2")
    pid = db.create_project("Suman")["id"]
    job = load(pid, make_zip(CHAT, FILES))
    assert job["info"]["media_skipped"] == 4
    assert statuses(pid, job["chat_id"]).count("skipped") == 4


def test_late_results_refresh_existing_passages(calls, monkeypatch):
    monkeypatch.setenv("ADDAMIND_MEDIA", "off")
    pid = db.create_project("Suman")["id"]
    job = load(pid, make_zip(CHAT, FILES))
    assert retrieval.search(Scope(pid), "bhool")["results"] == []
    monkeypatch.setenv("ADDAMIND_MEDIA", "on")
    media.process_chat(pid, job["chat_id"])
    hit = retrieval.search(Scope(pid), "bhool")["results"][0]
    assert hit["kind"] == "voice" and "bhool gaye" in hit["context"]


def test_pdf_text_is_read_and_bad_pdf_fails_cleanly():
    with pytest.raises(media.MediaError):
        media._pdf_text(b"%PDF-1.4 not really")
    with pytest.raises(media.Skip):
        media.analyse("document", b"x", None, "notes.docx", "")
    with pytest.raises(media.Skip):
        media.analyse("video", b"x" * (media.MAX_INLINE + 1), "video/mp4", "v.mp4", "")
