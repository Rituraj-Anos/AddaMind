"""AddaMind HTTP routes. Everything sits under /projects/{pid}, so no route can read across projects.

    POST   /projects                                  {"name"};  PATCH /projects/{pid} {"name"} renames
    GET    /projects, /projects/{pid}                 (get includes chats)
    DELETE /projects/{pid}                            removes all rows and files
    POST   /projects/{pid}/chats                      multipart `file` (.txt or .zip), optional `chat_id` to append
    GET    /projects/{pid}/chats, /chats/{cid}
    GET    /projects/{pid}/stats, /graph, /chats/{cid}/stats, /chats/{cid}/graph   (exact, no model)
    GET    /projects/{pid}/chats/{cid}/memory              timeline, topics, mood, jokes, dynamics
    GET    /projects/{pid}/participants/{part_id}/persona?chat_id=   built on first request
    DELETE /projects/{pid}/chats/{cid}
    GET    /projects/{pid}/jobs, /jobs/{jid}, /jobs/{jid}/events (SSE: one job JSON per change)
    GET    /projects/{pid}/chats/{cid}/messages?around=&before=&limit=
    GET    /projects/{pid}/messages/{mid}?context=
    GET    /projects/{pid}/search?q=&chat_id=&participant_id=&since=&until=&k=
    GET    /projects/{pid}/media/{media_id}
    POST   /projects/{pid}/agent   {agent, message, scope_type, scope_id, thread_id?, options} -> SSE
    GET    /projects/{pid}/threads?agent=&scope_type=&scope_id=, /threads/{tid};  DELETE /threads/{tid}
    POST   /projects/{pid}/tts {"text"} -> audio/wav (502: use the browser's voice)
    GET    /projects/{pid}/participants
    PATCH  /projects/{pid}/participants/{part_id}     {"is_me"?, "roast_opt_out"?}
    POST   /projects/{pid}/participants/{part_id}/merge {"into"}
"""
from __future__ import annotations

import json
import threading
import time
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from backend.api.store import to_display
from backend.core.llm import Message

from . import agents, analytics, db, ingest, memory, personas, retrieval, voice

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ParticipantPatch(BaseModel):
    is_me: bool | None = None
    roast_opt_out: bool | None = None


class MergeIn(BaseModel):
    into: int


def _project(pid: int) -> dict:
    p = db.get_project(pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


def _found(value, what: str):
    if value is None:
        raise HTTPException(404, f"{what} not found")
    return value


@router.post("", status_code=201)
def create_project(body: ProjectIn):
    return db.create_project(body.name.strip())


@router.get("")
def list_projects():
    return db.list_projects()


@router.get("/{pid}")
def get_project(pid: int):
    return {**_project(pid), "chats": db.list_chats(pid)}


@router.patch("/{pid}")
def rename_project(pid: int, body: ProjectIn):
    _project(pid)
    return db.rename_project(pid, body.name.strip())


@router.delete("/{pid}")
def delete_project(pid: int):
    return _found(db.delete_project(pid), "project")


# ---------------------------------------------------------------- chats and jobs
@router.post("/{pid}/chats", status_code=202)
def upload_chat(pid: int, file: UploadFile = File(...), chat_id: int | None = Form(None)):
    _project(pid)
    name = (file.filename or "chat.txt").replace("\\", "/").rsplit("/", 1)[-1]
    if not name.lower().endswith((".txt", ".zip")):
        raise HTTPException(400, "upload a WhatsApp export: the .txt file or the .zip")
    if chat_id is not None:
        _found(db.get_chat(pid, chat_id), "chat")
    job_id = ingest.create_job(pid, name, chat_id)
    try:
        ingest.save_upload(file.file, pid, job_id)
    except ValueError as e:
        ingest.fail_job(job_id, str(e))
        raise HTTPException(413, str(e))
    threading.Thread(target=ingest.run_job, args=(pid, job_id), daemon=True, name=f"ingest-{job_id}").start()
    return {"job_id": job_id}


@router.get("/{pid}/chats")
def list_chats(pid: int):
    _project(pid)
    return db.list_chats(pid)


@router.get("/{pid}/chats/{cid}")
def get_chat(pid: int, cid: int):
    return _found(db.get_chat(pid, cid), "chat")


@router.delete("/{pid}/chats/{cid}")
def delete_chat(pid: int, cid: int):
    return _found(db.delete_chat(pid, cid), "chat")


@router.get("/{pid}/stats")
def project_stats(pid: int):
    _project(pid)
    return analytics.stats(pid)


@router.get("/{pid}/graph")
def project_graph(pid: int):
    _project(pid)
    return analytics.graph(pid)


@router.get("/{pid}/chats/{cid}/stats")
def chat_stats(pid: int, cid: int):
    return _found(analytics.stats(pid, cid), "chat")


@router.get("/{pid}/chats/{cid}/graph")
def chat_graph(pid: int, cid: int):
    return _found(analytics.graph(pid, cid), "chat")


@router.get("/{pid}/chats/{cid}/memory")
def chat_memory(pid: int, cid: int):
    _found(db.get_chat(pid, cid), "chat")
    return _found(memory.get_memory(pid, cid), "memory (still processing?)")


@router.get("/{pid}/participants/{part_id}/persona")
def participant_persona(pid: int, part_id: int, chat_id: int | None = None):
    try:
        return _found(personas.get(pid, part_id, chat_id), "participant or chat")
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{pid}/jobs")
def list_jobs(pid: int):
    _project(pid)
    return db.list_jobs(pid)


@router.get("/{pid}/jobs/{jid}")
def get_job(pid: int, jid: int):
    return _found(db.get_job(pid, jid), "job")


@router.get("/{pid}/jobs/{jid}/events")
def job_events(pid: int, jid: int):
    _found(db.get_job(pid, jid), "job")

    def stream():
        last, quiet = None, 0.0
        while True:
            job = db.get_job(pid, jid)
            if job is None:
                yield f"data: {json.dumps({'type': 'gone', 'id': jid})}\n\n"
                return
            if job != last:
                yield f"data: {json.dumps({'type': 'job', **job}, ensure_ascii=False)}\n\n"
                last, quiet = job, 0.0
            if job["status"] in ("done", "failed"):
                return
            time.sleep(0.4)
            quiet += 0.4
            if quiet >= 10:
                yield ": keep-alive\n\n"
                quiet = 0.0

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- messages and media
@router.get("/{pid}/chats/{cid}/messages")
def chat_messages(pid: int, cid: int, around: int | None = None, before: int | None = None,
                  limit: int = Query(50, ge=1, le=200)):
    return _found(db.messages_window(pid, cid, around, before, limit), "chat or message")


@router.get("/{pid}/messages/{mid}")
def get_message(pid: int, mid: int, context: int = Query(5, ge=0, le=50)):
    return _found(db.get_message(pid, mid, context), "message")


@router.get("/{pid}/media/{media_id}")
def get_media(pid: int, media_id: int):
    row, path = _found(db.get_media(pid, media_id), "media")
    return FileResponse(path, media_type=row["mime"] or "application/octet-stream")


@router.get("/{pid}/search")
def search(pid: int, q: str = Query(min_length=1, max_length=300), chat_id: int | None = None,
           participant_id: int | None = None, since: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
           until: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), k: int = Query(8, ge=1, le=30)):
    _project(pid)
    if chat_id is not None:
        _found(db.get_chat(pid, chat_id), "chat")
    return retrieval.search(retrieval.Scope(pid, chat_id, participant_id), q, k, since, until)


# ---------------------------------------------------------------- agents and threads
class AgentOptions(BaseModel):
    tone: Literal["wholesome", "spicy", "savage"] | None = None
    style_of: str | None = Field(default=None, max_length=80)
    reply_to: int | None = None


class AgentIn(BaseModel):
    agent: Literal["analyzer", "roaster", "reply", "recall"]
    message: str = Field(min_length=1, max_length=4000)
    scope_type: Literal["project", "chat", "participant"] = "project"
    scope_id: int | None = None
    thread_id: int | None = None
    options: AgentOptions = AgentOptions()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post("/{pid}/agent")
def agent_chat(pid: int, body: AgentIn):
    """One agent turn as Server-Sent Events: thread, run_start, tool_call, tool_result, text_delta, ...,
    final (text with checked citations, cited messages, structured data) or error."""
    _project(pid)
    if body.thread_id is not None:
        thread = _found(db.get_thread(pid, body.thread_id), "thread")
        agent, scope_type, scope_id = thread["agent"], thread["scope_type"], thread["scope_id"]
        history = [Message.from_dict(m) for m in thread["messages"]]
        tid = thread["id"]
    else:
        agent, scope_type, scope_id, history = body.agent, body.scope_type, body.scope_id, []
        tid = None
    try:
        events = agents.run(pid, agent, body.message, scope_type, scope_id, history, body.options.model_dump())
        first = next(events)  # surfaces a bad scope as a 400 before the stream starts
    except ValueError as e:
        raise HTTPException(400, str(e))
    if tid is None:
        tid = db.create_thread(pid, agent, scope_type, scope_id, " ".join(body.message.split()))

    def stream():
        yield _sse({"type": "thread", "thread_id": tid, "agent": agent, "scope_type": scope_type, "scope_id": scope_id})
        for ev in _chain(first, events):
            if ev["type"] == "heartbeat":
                yield ": keep-alive\n\n"
                continue
            if ev["type"] == "final":
                db.append_thread(pid, tid, [m.to_dict() for m in ev["messages"]])
                ev = {k: v for k, v in ev.items() if k != "messages"}
            yield _sse(ev)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _chain(first, rest):
    yield first
    yield from rest


@router.get("/{pid}/threads")
def list_threads(pid: int, agent: str | None = None, scope_type: str | None = None, scope_id: int | None = None):
    _project(pid)
    return db.list_threads(pid, agent, scope_type, scope_id)


@router.get("/{pid}/threads/{tid}")
def get_thread(pid: int, tid: int):
    t = _found(db.get_thread(pid, tid), "thread")
    msgs = [Message.from_dict(m) for m in t["messages"]]
    shown = to_display(msgs)
    for d, m in zip(shown, msgs):
        if m.role == "assistant" and m.meta.get("citations") is not None:
            d["citations"] = [x for i in m.meta["citations"] if (x := db.get_message(pid, i, 0)) and (x := x["message"])]
    return {**{k: v for k, v in t.items() if k != "messages"}, "messages": shown}


@router.delete("/{pid}/threads/{tid}")
def delete_thread(pid: int, tid: int):
    if not db.delete_thread(pid, tid):
        raise HTTPException(404, "thread not found")
    return {"deleted": tid}


# ---------------------------------------------------------------- participants
class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=voice.MAX_CHARS)


@router.post("/{pid}/tts")
def speak(pid: int, body: SpeakIn):
    """A roast read aloud as WAV. 502 tells the client to fall back to the browser's voice."""
    _project(pid)
    try:
        audio = voice.speak(body.text)
    except voice.VoiceError as e:
        raise HTTPException(502, f"text to speech failed: {e}")
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/{pid}/participants")
def list_participants(pid: int):
    _project(pid)
    return db.list_participants(pid)


@router.patch("/{pid}/participants/{part_id}")
def update_participant(pid: int, part_id: int, body: ParticipantPatch):
    if not db.update_participant(pid, part_id, body.is_me, body.roast_opt_out):
        raise HTTPException(404, "participant not found")
    return next(p for p in db.list_participants(pid) if p["id"] == part_id)


@router.post("/{pid}/participants/{part_id}/merge")
def merge_participant(pid: int, part_id: int, body: MergeIn):
    if not db.merge_participants(pid, part_id, body.into):
        raise HTTPException(400, "both participants must exist in this project and be different")
    return next(p for p in db.list_participants(pid) if p["id"] == body.into)
