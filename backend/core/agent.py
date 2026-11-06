"""The agent loop: call the model, run requested tools, feed results back, repeat.

It reports progress as plain-dict events so any front end (CLI, SSE, Streamlit) can show
what the agent is doing:

    run_start, step, llm_attempt, llm_error, llm_skip, llm_response, text_delta, text_reset,
    tool_call, tool_result, structuring, final (text, data?, data_error?), error
"""
from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterator

from pydantic import BaseModel

from .llm import AllModelsFailed, LLMRouter, Message, get_router
from .structured import structured
from .tools import ToolRegistry, registry as default_registry, result_to_text

Emit = Callable[[dict], None]


@dataclass
class AgentConfig:
    name: str = "Agent"
    system_prompt: str = "You are {name}, a helpful AI agent. Today is {today}."
    tools: list[str] | None = None  # None = all registered tools
    max_steps: int = 8
    temperature: float | None = None
    # Stream answer text as text_delta events while the model writes it.
    stream: bool = True
    # After the answer, also return validated JSON of this shape in final["data"] (see structured.py).
    output_schema: type[BaseModel] | None = None
    # Called on every step; its text is appended to the system prompt (e.g. the uploaded files list).
    context: Callable[[], str] | None = None


class Agent:
    def __init__(self, config: AgentConfig | None = None, *, tools: ToolRegistry | None = None,
                 router: LLMRouter | None = None):
        self.config = config or AgentConfig()
        self.tools = tools or default_registry
        self.router = router or get_router()

    def _system(self) -> Message:
        text = self.config.system_prompt.format(name=self.config.name, today=date.today().isoformat())
        if self.config.context:
            extra = self.config.context()
            if extra:
                text += "\n\n" + extra
        return Message("system", text)

    def _structure(self, msgs: list[Message], answer: str, emit: Emit) -> tuple[dict | None, str | None]:
        """Turn the finished answer into validated JSON. Failure keeps the text answer."""
        emit({"type": "structuring", "schema": self.config.output_schema.__name__})
        ask = msgs + [Message("assistant", answer), Message(
            "user", "Now return the final result as a JSON object that matches the schema. "
                    "Use only facts from this conversation and the tool results above.")]
        try:
            data = structured(ask, self.config.output_schema, router=self.router, on_event=emit)
            return data.model_dump(mode="json"), None
        except AllModelsFailed:
            raise
        except Exception as e:  # noqa: BLE001
            return None, str(e)[:300]

    def _run(self, user_text: str, history: list[Message], emit: Emit) -> list[Message]:
        """Core loop. Returns the new messages produced this turn (user, assistant, tool...)."""
        cfg = self.config
        specs = self.tools.specs(cfg.tools)
        new: list[Message] = [Message("user", user_text)]
        t_run = time.perf_counter()

        for step in range(1, cfg.max_steps + 1):
            emit({"type": "step", "step": step})
            last_step = step == cfg.max_steps
            msgs = [self._system(), *history, *new]
            on_text = (lambda piece, s=step: emit({"type": "text_delta", "step": s, "text": piece})) \
                if cfg.stream else None
            # On the last allowed step, withhold tools so the model must answer.
            resp = self.router.chat(msgs, None if last_step else specs or None,
                                    temperature=cfg.temperature, on_event=emit, on_text=on_text)
            if last_step and resp.tool_calls:
                # Some models still call tools when none are offered. Their calls can't run: keep the text.
                resp.tool_calls = []
                resp.text = resp.text or "I ran out of steps before finishing. Please ask a narrower question."
            answer = resp.to_message()
            new.append(answer)
            if not resp.tool_calls:
                final = {"type": "final", "text": resp.text, "steps": step,
                         "provider": resp.provider, "model": resp.model}
                if cfg.output_schema:
                    data, err = self._structure(msgs, resp.text, emit)
                    final["data"] = data
                    if err:
                        final["data_error"] = err
                    answer.meta = {**answer.meta, "data": data}  # stored, so history can show it
                final["duration_ms"] = int((time.perf_counter() - t_run) * 1000)
                emit(final)
                return new
            for tc in resp.tool_calls:
                emit({"type": "tool_call", "id": tc.id, "name": tc.name, "args": tc.args})
                ok, result, ms = self.tools.execute(tc.name, tc.args, cfg.tools)
                text = result_to_text(result)
                emit({"type": "tool_result", "id": tc.id, "name": tc.name, "ok": ok,
                      "duration_ms": ms, "result": result if len(text) < 4000 else text[:4000]})
                new.append(Message("tool", text, tool_call_id=tc.id, name=tc.name))
        raise RuntimeError("unreachable: last step runs without tools")

    def run_stream(self, user_text: str, history: list[Message] | None = None,
                   heartbeat_s: float | None = None) -> Iterator[dict]:
        """Yield events live while the agent runs in a worker thread.
        The last event is 'final' (includes 'messages' to append to history) or 'error'.
        With heartbeat_s, yields {"type": "heartbeat"} when nothing happened for that long
        (keeps HTTP streams alive while a slow model is thinking)."""
        run_id = uuid.uuid4().hex[:8]
        q: queue.Queue = queue.Queue()
        done = object()

        def worker():
            try:
                new = self._run(user_text, list(history or []), q.put)
                q.put({"type": "_messages", "messages": new})
            except AllModelsFailed as e:
                q.put({"type": "error", "kind": "all_models_failed", "message": str(e)})
            except Exception as e:  # noqa: BLE001 - surface any failure as an event
                q.put({"type": "error", "kind": type(e).__name__, "message": str(e)})
            finally:
                q.put(done)

        yield {"type": "run_start", "run_id": run_id, "agent": self.config.name}
        threading.Thread(target=worker, daemon=True).start()
        final = None
        while True:
            try:
                ev = q.get(timeout=heartbeat_s)
            except queue.Empty:
                yield {"type": "heartbeat", "run_id": run_id}
                continue
            if ev is done:
                break
            if ev["type"] == "final":
                final = ev  # emit after messages are attached
            elif ev["type"] == "_messages":
                if final:
                    yield {**final, "run_id": run_id, "messages": ev["messages"]}
            else:
                yield {**ev, "run_id": run_id}

    def run(self, user_text: str, history: list[Message] | None = None,
            on_event: Emit | None = None) -> tuple[str, list[Message]]:
        """Blocking call. Returns (answer, new_messages). Raises on failure."""
        for ev in self.run_stream(user_text, history):
            if on_event:
                on_event(ev)
            if ev["type"] == "final":
                return ev["text"], ev["messages"]
            if ev["type"] == "error":
                raise RuntimeError(ev["message"])
        raise RuntimeError("agent ended without an answer")
