"""Any OpenAI-compatible /chat/completions endpoint: Groq, NVIDIA NIM, Ollama, OpenRouter..."""
from __future__ import annotations

import json
import re
import time

from .base import Provider
from .errors import LLMError
from .types import LLMResponse, Message, ToolCall, ToolSpec, new_call_id

_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class _ThinkFilter:
    """Streaming version of _THINK: drops <think>...</think> even when tags are split across chunks."""
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.buf = ""
        self.inside = False

    def feed(self, piece: str) -> str:
        self.buf += piece
        out = []
        while self.buf:
            tag = self.CLOSE if self.inside else self.OPEN
            i = self.buf.find(tag)
            if i >= 0:
                if not self.inside:
                    out.append(self.buf[:i])
                self.buf = self.buf[i + len(tag):]
                self.inside = not self.inside
                if not self.inside:
                    self.buf = self.buf.lstrip()
                continue
            # Keep a possible partial tag at the end for the next chunk.
            keep = next((k for k in range(len(tag) - 1, 0, -1) if self.buf.endswith(tag[:k])), 0)
            if not self.inside:
                out.append(self.buf[:len(self.buf) - keep])
            self.buf = self.buf[len(self.buf) - keep:] if keep else ""
            break
        return "".join(out)


_LEAKED_CALL = re.compile(r"<tool_call>|<function=\w+>|<\|tool_call", re.I)


class OpenAICompatProvider(Provider):
    def _check_leak(self, text: str, calls: list) -> None:
        """Some hosted models write a tool call into the text instead of the tool_calls field.
        That answer is unusable, so fail it and let the router try the next model."""
        if text and not calls and _LEAKED_CALL.search(text):
            raise self._err("bad_response", "tool call written as text")

    def __init__(self, provider: str, base_url: str, model: str, *,
                 extra_headers: dict | None = None, **kw):
        super().__init__(model, **kw)
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.extra_headers = extra_headers or {}

    @staticmethod
    def _messages(messages: list[Message]) -> list[dict]:
        out = []
        for m in messages:
            if m.role == "assistant":
                d: dict = {"role": "assistant", "content": m.text or ""}
                if m.tool_calls:
                    d["tool_calls"] = [{"id": tc.id, "type": "function",
                                        "function": {"name": tc.name, "arguments": json.dumps(tc.args)}}
                                       for tc in m.tool_calls]
                out.append(d)
            elif m.role == "tool":
                out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.text})
            else:
                out.append({"role": m.role, "content": m.text})
        return out

    def _args(self, raw) -> dict:
        try:
            args = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            raise self._err("bad_response", f"tool call arguments were not valid JSON: {str(raw)[:80]}")
        return args or {}

    def _stream(self, url: str, headers: dict, body: dict, on_text) -> LLMResponse:
        """stream=true: text deltas go to on_text (minus <think> blocks); tool calls are
        assembled from their per-index argument fragments."""
        t0 = time.perf_counter()
        body = {**body, "stream": True}
        text_parts: list[str] = []
        calls: dict[int, dict] = {}
        usage: dict = {}
        think = _ThinkFilter()
        for chunk in self._post_stream(url, headers, body):
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    visible = think.feed(delta["content"])
                    if visible:
                        text_parts.append(visible)
                        on_text(visible)
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", len(calls)), {"id": None, "name": "", "args": ""})
                    slot["id"] = tc.get("id") or slot["id"]
                    fn = tc.get("function") or {}
                    slot["name"] += fn.get("name") or ""
                    slot["args"] += fn.get("arguments") or ""
        text = "".join(text_parts).strip()
        tool_calls = [ToolCall(id=c["id"] or new_call_id(), name=c["name"], args=self._args(c["args"] or "{}"))
                      for _, c in sorted(calls.items()) if c["name"]]
        if not text and not tool_calls:
            raise self._err("bad_response", "no text or tool call")
        self._check_leak(text, tool_calls)
        return LLMResponse(text=text, tool_calls=tool_calls, provider=self.provider, model=self.model,
                           latency_ms=int((time.perf_counter() - t0) * 1000),
                           usage={"input_tokens": usage.get("prompt_tokens"),
                                  "output_tokens": usage.get("completion_tokens")},
                           meta={"provider": self.provider, "model": self.model})

    def chat(self, messages, tools=None, json_schema=None, temperature=None, max_tokens=None, on_text=None):
        body: dict = {"model": self.model, "messages": self._messages(messages)}
        if tools:
            body["tools"] = [{"type": "function", "function": {
                "name": t.name, "description": t.description, "parameters": t.parameters}} for t in tools]
            body["tool_choice"] = "auto"
        if temperature is not None:
            body["temperature"] = temperature
        body["max_tokens"] = max_tokens or 4096
        if json_schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "output", "schema": json_schema}}

        headers = {**self.extra_headers}
        if self.key_env:
            headers["Authorization"] = f"Bearer {self._api_key()}"
        url = f"{self.base_url}/chat/completions"
        if on_text and not json_schema:
            return self._stream(url, headers, body, on_text)
        try:
            data, latency = self._post(url, headers, body)
        except LLMError as e:
            if not (json_schema and e.kind == "bad_request"):
                raise
            # Model doesn't support json_schema: fall back to plain JSON mode + schema in the prompt.
            body["response_format"] = {"type": "json_object"}
            body["messages"].insert(0, {"role": "system", "content":
                "Reply with only a JSON object matching this JSON Schema:\n" + json.dumps(json_schema)})
            data, latency = self._post(url, headers, body)

        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise self._err("bad_response", "no choices in response")
        text = _THINK.sub("", msg.get("content") or "").strip()
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            calls.append(ToolCall(id=tc.get("id") or new_call_id(), name=fn.get("name", ""),
                                  args=self._args(fn.get("arguments") or "{}")))
        if not text and not calls:
            raise self._err("bad_response", "no text or tool call")
        self._check_leak(text, calls)

        u = data.get("usage") or {}
        return LLMResponse(text=text, tool_calls=calls, provider=self.provider, model=self.model,
                           latency_ms=latency,
                           usage={"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens")},
                           meta={"provider": self.provider, "model": self.model})
