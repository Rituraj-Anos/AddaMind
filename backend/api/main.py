"""HTTP API over the agent core.

Run locally:
    .\\.venv\\Scripts\\python.exe -m uvicorn backend.api.main:app --reload --port 8000

Endpoints:
    GET    /health                     liveness (no LLM call; safe for uptime pings)
    GET    /profile                    agent name, tagline, sample prompts, tools (for the UI)
    GET    /models                     router chain, sticky model, cooldowns
    POST   /chat                       {"message", "conversation_id"?} -> Server-Sent Events
    GET    /conversations              list, newest first
    GET    /conversations/{id}         messages for display
    DELETE /conversations/{id}

/chat streams one JSON object per SSE `data:` line. Event types are those of Agent.run_stream
(run_start, step, llm_attempt, llm_error, llm_skip, llm_response, tool_call, tool_result, final,
error), preceded by {"type": "conversation", "conversation_id": ...}. Keep-alives are SSE comments.
"""
from __future__ import annotations

import dataclasses
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend import profile
from backend.core import keys as api_keys
from backend.core.agent import Agent
from backend.core.config import env_str
from backend.core.documents import ALLOWED, MAX_BYTES, get_store
from backend.core.llm import get_router
from backend.core.tools import registry

from backend.chatintel import db as chatintel_db
from backend.chatintel import api as chatintel_api
from backend.chatintel.api import router as chatintel_router

from .store import ID_PATTERN, ConversationStore, to_display

@asynccontextmanager
async def lifespan(_app: FastAPI):
    chatintel_db.load_seed()
    chatintel_db.recover_jobs()
    chatintel_api.start_cleanup()
    yield


app = FastAPI(title=f"{profile.NAME} API", version="0.1.0", lifespan=lifespan)
app.include_router(chatintel_router)

# Comma-separated exact origins (set your Vercel URL here when deploying), plus a regex.
# The default regex allows any localhost port, since `next dev` moves to 3001+ when 3000 is busy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in env_str("CORS_ORIGINS").split(",") if o.strip()],
    allow_origin_regex=env_str("CORS_ORIGIN_REGEX", r"http://(localhost|127\.0\.0\.1)(:\d+)?"),
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Visitor"],
)

store = ConversationStore()
agent = Agent(profile.AGENT)


def _jsonable(o):
    if isinstance(o, BaseModel):
        return o.model_dump()
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    return str(o)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=_jsonable)}\n\n"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    conversation_id: str | None = Field(default=None, pattern=ID_PATTERN)


@app.get("/health")
def health():
    return {"status": "ok", "agent": profile.NAME,
            "models_available": sum(1 for m in get_router().status()["chain"] if m["available"]),
            # How many API keys each provider has, ready or resting or refused. Never the keys themselves.
            "keys": {name: api_keys.status(f"{name.upper()}_API_KEY") for name in ("gemini", "groq", "nvidia", "openrouter")},
            # A public server keeps uploads private to the browser that sent them and deletes them after this long.
            "public": chatintel_api.public(), "retention_hours": chatintel_api.retention_hours()}


@app.get("/profile")
def get_profile():
    specs = registry.specs(profile.AGENT.tools)
    schema = profile.AGENT.output_schema
    return {"name": profile.NAME, "tagline": profile.TAGLINE, "sample_prompts": profile.SAMPLE_PROMPTS,
            "tools": [{"name": s.name, "description": s.description} for s in specs],
            "output_schema": schema.__name__ if schema else None,
            "upload": {"accept": sorted(ALLOWED), "max_mb": MAX_BYTES // 1024 // 1024}}


@app.get("/models")
def models():
    return get_router().status()


@app.post("/chat")
def chat(req: ChatRequest):
    cid = req.conversation_id or store.new_id()
    history = store.messages(cid)

    def stream():
        yield _sse({"type": "conversation", "conversation_id": cid})
        for ev in agent.run_stream(req.message, history, heartbeat_s=10):
            if ev["type"] == "heartbeat":
                yield ": keep-alive\n\n"
                continue
            if ev["type"] == "final":
                store.append(cid, ev["messages"])  # failed turns are not saved, so a retry is clean
                ev = {k: v for k, v in ev.items() if k != "messages"}
            yield _sse(ev)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/conversations")
def list_conversations():
    return store.list()


@app.get("/conversations/{cid}")
def get_conversation(cid: str):
    try:
        data = store.get(cid)
    except ValueError:
        raise HTTPException(400, "invalid conversation id")
    if not data:
        raise HTTPException(404, "conversation not found")
    return {"id": data["id"], "title": data["title"], "updated_at": data.get("updated_at"),
            "messages": to_display(store.messages(cid))}


@app.delete("/conversations/{cid}")
def delete_conversation(cid: str):
    try:
        deleted = store.delete(cid)
    except ValueError:
        raise HTTPException(400, "invalid conversation id")
    if not deleted:
        raise HTTPException(404, "conversation not found")
    return {"deleted": cid}


# ---------------------------------------------------------------- documents
def _doc_json(d) -> dict:
    return {"id": d.id, "name": d.name, "size": d.size, "pages": d.pages, "chunks": d.chunks,
            "chars": d.chars, "uploaded_at": d.uploaded_at}


@app.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    data = await file.read(MAX_BYTES + 1)
    try:
        info = get_store().add(file.filename or "upload.txt", data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001 - corrupt PDFs etc.
        raise HTTPException(400, f"could not read the file: {type(e).__name__}")
    return _doc_json(info)


@app.get("/documents")
def list_documents():
    return [_doc_json(d) for d in get_store().list()]


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    if not get_store().delete(doc_id):
        raise HTTPException(404, "document not found")
    return {"deleted": doc_id}
