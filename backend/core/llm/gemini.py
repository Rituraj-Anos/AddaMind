"""Gemini via the REST generateContent API.

Gemini 3 models return a thoughtSignature on function-call parts and reject the next
request (400) if it is missing. We therefore keep the raw model parts in Message.meta
and send them back unchanged when continuing on the same model. When the history came
from another provider or another Gemini model, we rebuild the parts and use Google's
documented placeholder signature.
"""
from __future__ import annotations

import json
import time

from .base import Provider
from .types import LLMResponse, Message, ToolCall, ToolSpec, new_call_id

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
SKIP_SIGNATURE = "skip_thought_signature_validator"


def _as_object(text: str) -> dict:
    try:
        v = json.loads(text)
    except (TypeError, ValueError):
        return {"result": text}
    return v if isinstance(v, dict) else {"result": v}


class GeminiProvider(Provider):
    provider = "gemini"

    def _contents(self, messages: list[Message]) -> tuple[str, list[dict]]:
        system = "\n\n".join(m.text for m in messages if m.role == "system" and m.text)
        contents: list[dict] = []
        native_ids: set[str] = set()  # call ids Gemini itself issued (safe to echo back)

        for m in messages:
            if m.role == "system":
                continue
            if m.role == "user":
                contents.append({"role": "user", "parts": [{"text": m.text or " "}]})
            elif m.role == "assistant":
                raw = m.meta.get("gemini_parts")
                if raw and m.meta.get("model") == self.model:
                    parts = raw
                    native_ids |= {p["functionCall"].get("id") for p in raw if "functionCall" in p}
                else:
                    parts = [{"text": m.text}] if m.text else []
                    for i, tc in enumerate(m.tool_calls):
                        p = {"functionCall": {"name": tc.name, "args": tc.args}}
                        if i == 0:
                            p["thoughtSignature"] = SKIP_SIGNATURE
                        parts.append(p)
                contents.append({"role": "model", "parts": parts or [{"text": " "}]})
            elif m.role == "tool":
                fr = {"name": m.name or "tool", "response": _as_object(m.text)}
                if m.tool_call_id in native_ids:
                    fr["id"] = m.tool_call_id
                part = {"functionResponse": fr}
                # Consecutive tool results belong in one user turn.
                if contents and contents[-1].get("_tool"):
                    contents[-1]["parts"].append(part)
                else:
                    contents.append({"role": "user", "parts": [part], "_tool": True})
        for c in contents:
            c.pop("_tool", None)
        return system, contents

    def chat(self, messages, tools=None, json_schema=None, temperature=None, max_tokens=None, on_text=None):
        system, contents = self._contents(messages)
        body: dict = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [{"functionDeclarations": [
                {"name": t.name, "description": t.description, "parametersJsonSchema": t.parameters}
                for t in tools]}]
        gen: dict = {}
        if temperature is not None:
            gen["temperature"] = temperature
        if max_tokens:
            gen["maxOutputTokens"] = max_tokens
        if json_schema:
            gen["responseMimeType"] = "application/json"
            gen["responseJsonSchema"] = json_schema
        if gen:
            body["generationConfig"] = gen

        headers = {"x-goog-api-key": self._api_key()}
        if on_text and not json_schema:
            return self._stream(body, headers, on_text)

        data, latency = self._post(f"{BASE_URL}/{self.model}:generateContent", headers, body)

        cands = data.get("candidates") or []
        if not cands:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise self._err("bad_response", f"empty response ({reason})")
        cand = cands[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        calls = [ToolCall(id=p["functionCall"].get("id") or new_call_id(),
                          name=p["functionCall"]["name"],
                          args=p["functionCall"].get("args") or {})
                 for p in parts if "functionCall" in p]
        if not text.strip() and not calls:
            raise self._err("bad_response", f"no text or tool call (finishReason={cand.get('finishReason')})")

        um = data.get("usageMetadata") or {}
        return LLMResponse(
            text=text, tool_calls=calls, provider=self.provider, model=self.model, latency_ms=latency,
            usage={"input_tokens": um.get("promptTokenCount"), "output_tokens": um.get("candidatesTokenCount")},
            meta={"provider": self.provider, "model": self.model, "gemini_parts": parts},
        )

    def _stream(self, body: dict, headers: dict, on_text) -> LLMResponse:
        """streamGenerateContent over SSE. Parts are kept exactly as received (not merged) so
        thought signatures, which can arrive on any part, are echoed back unchanged."""
        t0 = time.perf_counter()
        parts: list[dict] = []
        usage: dict = {}
        finish = None
        for chunk in self._post_stream(f"{BASE_URL}/{self.model}:streamGenerateContent?alt=sse", headers, body):
            if (chunk.get("promptFeedback") or {}).get("blockReason"):
                raise self._err("bad_response", f"blocked ({chunk['promptFeedback']['blockReason']})")
            usage = chunk.get("usageMetadata") or usage
            for cand in chunk.get("candidates") or []:
                finish = cand.get("finishReason") or finish
                for p in (cand.get("content") or {}).get("parts") or []:
                    parts.append(p)
                    if p.get("text") and not p.get("thought"):
                        on_text(p["text"])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        calls = [ToolCall(id=p["functionCall"].get("id") or new_call_id(), name=p["functionCall"]["name"],
                          args=p["functionCall"].get("args") or {})
                 for p in parts if "functionCall" in p]
        if not text.strip() and not calls:
            raise self._err("bad_response", f"no text or tool call (finishReason={finish})")
        return LLMResponse(
            text=text, tool_calls=calls, provider=self.provider, model=self.model,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            usage={"input_tokens": usage.get("promptTokenCount"), "output_tokens": usage.get("candidatesTokenCount")},
            meta={"provider": self.provider, "model": self.model, "gemini_parts": parts},
        )
