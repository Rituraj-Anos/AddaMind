"""Ordered fallback across providers with a sticky model, cooldowns and exponential backoff.

Order: the last model that worked (if used within STICKY_TTL) goes first, then LLM_CHAIN order.
A failing model is put on cooldown so later calls skip it instead of waiting on it again:
  rate_limit -> Retry-After / Gemini retryDelay, else 60s;  overloaded/timeout/network -> 30s * 2^(consecutive failures-1), max 10 min;
  not_found -> 1 hour;  auth -> whole provider skipped until restart.
State is saved to .cache/llm_state.json so `uvicorn --reload` restarts keep it.
"""
from __future__ import annotations

import json
import random
import threading
import time
from typing import Callable

from ..config import CACHE_DIR, env_float, env_int, env_str
from .base import Provider
from .errors import AllModelsFailed, LLMError
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatProvider
from .types import LLMResponse, Message, ToolSpec

EventFn = Callable[[dict], None]

DEFAULT_CHAIN = ("gemini:gemini-3.8-flash,gemini:gemini-3.6-flash,gemini:gemini-3.5-flash-lite,"
                 "groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b,"
                 "openrouter:nvidia/nemotron-3.5-lightning:free,openrouter:openrouter/auto,"
                 "nvidia:mistralai/mistral-large-4-1t-a52b")

STATE_FILE = CACHE_DIR / "llm_state.json"


def estimate_tokens(messages: list[Message], tools: list[ToolSpec] | None) -> int:
    chars = sum(len(m.text) + sum(len(json.dumps(tc.args)) for tc in m.tool_calls) for m in messages)
    if tools:
        chars += sum(len(t.description) + len(json.dumps(t.parameters)) for t in tools)
    return chars // 4


def build_provider(spec: str) -> Provider:
    """'provider:model' -> Provider. Model ids may contain ':' or '/'."""
    name, _, model = spec.strip().partition(":")
    timeout = env_float("LLM_TIMEOUT_S", 30)
    if name == "gemini":
        return GeminiProvider(model, key_env="GEMINI_API_KEY", timeout_s=timeout)
    if name == "groq":
        return OpenAICompatProvider("groq", "https://api.groq.com/openai/v1", model,
                                    key_env="GROQ_API_KEY", timeout_s=timeout,
                                    max_prompt_tokens=env_int("GROQ_MAX_PROMPT_TOKENS", 6000))
    if name == "nvidia":
        return OpenAICompatProvider("nvidia", "https://integrate.api.nvidia.com/v1", model,
                                    key_env="NVIDIA_API_KEY", timeout_s=env_float("NVIDIA_TIMEOUT_S", 60))
    if name == "openrouter":
        return OpenAICompatProvider("openrouter", "https://openrouter.ai/api/v1", model,
                                    key_env="OPENROUTER_API_KEY", timeout_s=env_float("OPENROUTER_TIMEOUT_S", 45),
                                    extra_headers={"HTTP-Referer": env_str("OPENROUTER_REFERER",
                                                                           "https://github.com/hackathon-agent"),
                                                   "X-Title": env_str("OPENROUTER_TITLE", "hackathon-agent")})
    if name == "ollama":  # optional local emergency fallback; only used if listed in LLM_CHAIN
        return OpenAICompatProvider("ollama", env_str("OLLAMA_BASE_URL", "http://localhost:11434/v1"), model,
                                    key_env=None, timeout_s=env_float("OLLAMA_TIMEOUT_S", 120))
    raise ValueError(f"Unknown provider '{name}' in LLM_CHAIN entry '{spec}'")


class LLMRouter:
    def __init__(self, providers: list[Provider], *, sticky_ttl_s: float = 900, rounds: int = 2,
                 persist: bool = True):
        self.providers = providers
        self.sticky_ttl_s = sticky_ttl_s
        self.rounds = rounds
        self.persist = persist
        self._lock = threading.Lock()
        self._dead_providers: set[str] = set()  # auth failures, in-memory only
        self._state = {"sticky": None, "sticky_at": 0.0, "cooldown": {}, "failures": {}}
        self._load()

    # ---------- state ----------
    def _load(self):
        if self.persist and STATE_FILE.exists():
            try:
                self._state.update(json.loads(STATE_FILE.read_text()))
            except ValueError:
                pass

    def _save(self):
        if not self.persist:
            return
        CACHE_DIR.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps(self._state, indent=1))

    def _record_success(self, p: Provider):
        with self._lock:
            s = self._state
            s["sticky"], s["sticky_at"] = p.key, time.time()
            s["cooldown"].pop(p.key, None)
            s["failures"].pop(p.key, None)
            self._save()

    def _record_failure(self, p: Provider, e: LLMError) -> float:
        with self._lock:
            s = self._state
            n = s["failures"].get(p.key, 0) + 1
            s["failures"][p.key] = n
            if e.kind == "auth":
                self._dead_providers.add(p.provider)
                cool = 0.0
            elif e.kind == "not_found":
                cool = 3600.0
            elif e.kind == "rate_limit":
                cool = min(e.retry_after or 60.0, 900.0)
            elif e.kind in ("overloaded", "timeout", "network"):
                cool = min(30.0 * 2 ** (n - 1), 600.0)
            else:  # bad_request / bad_response: try others now, this model again soon
                cool = 10.0
            if cool:
                s["cooldown"][p.key] = time.time() + cool
            if s["sticky"] == p.key:
                s["sticky"] = None
            self._save()
            return cool

    def _ordered(self) -> list[Provider]:
        s = self._state
        ps = [p for p in self.providers if p.available() and p.provider not in self._dead_providers]
        if s["sticky"] and time.time() - s["sticky_at"] < self.sticky_ttl_s:
            ps.sort(key=lambda p: p.key != s["sticky"])  # stable: sticky first, rest keep order
        return ps

    def status(self) -> dict:
        now = time.time()
        return {
            "sticky": self._state["sticky"],
            "chain": [{"key": p.key, "available": p.available() and p.provider not in self._dead_providers,
                       "cooldown_s": max(0, int(self._state["cooldown"].get(p.key, 0) - now))}
                      for p in self.providers],
        }

    # ---------- call ----------
    def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None, *,
             json_schema: dict | None = None, temperature: float | None = None,
             max_tokens: int | None = None, on_event: EventFn | None = None,
             on_text: Callable[[str], None] | None = None) -> LLMResponse:
        """on_text streams visible answer text. If a model fails mid-stream, a text_reset event
        is emitted before falling back, so the UI can drop that model's partial text."""
        emit = on_event or (lambda e: None)
        est = estimate_tokens(messages, tools)
        errors: list[LLMError] = []

        for rnd in range(self.rounds):
            tried = False
            for p in self._ordered():
                until = self._state["cooldown"].get(p.key, 0)
                if rnd == 0 and until > time.time():
                    continue  # cooling down; may still be tried in the last-resort round
                if p.max_prompt_tokens and est > p.max_prompt_tokens:
                    emit({"type": "llm_skip", "provider": p.provider, "model": p.model,
                          "reason": f"prompt ~{est} tokens > limit {p.max_prompt_tokens}"})
                    continue
                tried = True
                emit({"type": "llm_attempt", "provider": p.provider, "model": p.model})
                streamed = False

                def text_cb(piece: str):
                    nonlocal streamed
                    streamed = True
                    on_text(piece)

                try:
                    resp = p.chat(messages, tools, json_schema=json_schema, temperature=temperature,
                                  max_tokens=max_tokens, on_text=text_cb if on_text else None)
                except LLMError as e:
                    errors.append(e)
                    cool = self._record_failure(p, e)
                    if streamed:  # partial text from the failed model must be discarded by the UI
                        emit({"type": "text_reset", "provider": p.provider, "model": p.model})
                    emit({"type": "llm_error", "provider": p.provider, "model": p.model,
                          "kind": e.kind, "status": e.status, "cooldown_s": int(cool)})
                    continue
                self._record_success(p)
                emit({"type": "llm_response", "provider": p.provider, "model": p.model,
                      "latency_ms": resp.latency_ms, "usage": resp.usage,
                      "tool_calls": len(resp.tool_calls)})
                return resp
            if rnd < self.rounds - 1:
                # Everything failed or was cooling down: back off briefly, then retry ignoring cooldowns.
                time.sleep((1.5 if tried else 0.2) * 2 ** rnd + random.uniform(0, 0.5))
        raise AllModelsFailed(errors)


_router: LLMRouter | None = None


def get_router() -> LLMRouter:
    """Process-wide router built from LLM_CHAIN."""
    global _router
    if _router is None:
        chain = env_str("LLM_CHAIN") or DEFAULT_CHAIN
        _router = LLMRouter([build_provider(s) for s in chain.split(",") if s.strip()],
                            sticky_ttl_s=env_float("LLM_STICKY_TTL_S", 900))
    return _router
