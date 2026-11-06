"""Conversation storage: one JSON file per conversation in .cache/conversations/.

Files survive `uvicorn --reload` restarts during development. On Render's free tier the disk is
wiped on redeploy, which is fine for a demo. Full messages (including Gemini thought signatures in
`meta`) are stored so a conversation can continue on the same model.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

from backend.core.config import CACHE_DIR
from backend.core.llm import Message

ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
_ID = re.compile(ID_PATTERN)


class ConversationStore:
    def __init__(self, directory: Path = CACHE_DIR / "conversations"):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]

    def _path(self, cid: str) -> Path:
        if not _ID.match(cid or ""):  # ids become file names: never allow path characters
            raise ValueError("invalid conversation id")
        return self.dir / f"{cid}.json"

    def get(self, cid: str) -> dict | None:
        p = self._path(cid)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None

    def messages(self, cid: str) -> list[Message]:
        data = self.get(cid)
        return [Message.from_dict(m) for m in data["messages"]] if data else []

    def append(self, cid: str, new: list[Message]) -> None:
        with self._lock:
            now = time.time()
            data = self.get(cid) or {"id": cid, "created_at": now, "title": "", "messages": []}
            if not data["title"]:
                first = next((m.text for m in new if m.role == "user"), "New conversation")
                data["title"] = " ".join(first.split())[:60]
            data["messages"] += [m.to_dict() for m in new]
            data["updated_at"] = now
            p = self._path(cid)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(p)  # atomic on the same filesystem

    def list(self) -> list[dict]:
        items = []
        for p in self.dir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            items.append({"id": d["id"], "title": d.get("title", ""), "updated_at": d.get("updated_at", 0),
                          "message_count": sum(1 for m in d["messages"] if m["role"] in ("user", "assistant")
                                               and m.get("text"))})
        return sorted(items, key=lambda x: x["updated_at"], reverse=True)

    def delete(self, cid: str) -> bool:
        p = self._path(cid)
        if p.exists():
            p.unlink()
            return True
        return False


def to_display(messages: list[Message]) -> list[dict]:
    """Messages as the UI needs them: no provider metadata, tool results trimmed."""
    out = []
    for m in messages:
        if m.role == "user":
            out.append({"role": "user", "text": m.text})
        elif m.role == "assistant":
            d = {"role": "assistant", "text": m.text,
                 "tool_calls": [{"id": tc.id, "name": tc.name, "args": tc.args} for tc in m.tool_calls]}
            if m.meta.get("data") is not None:
                d["data"] = m.meta["data"]  # structured output, if the profile asked for it
            out.append(d)
        elif m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "name": m.name, "text": m.text[:2000]})
    return out
