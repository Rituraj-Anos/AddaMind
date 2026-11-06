"""Common provider interface and shared HTTP handling."""
from __future__ import annotations

import json
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Callable, Iterator

import requests

from .errors import LLMError, kind_from_status
from .types import LLMResponse, Message, ToolSpec

TextFn = Callable[[str], None]
CONNECT_TIMEOUT_S = 5
_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')


class Provider(ABC):
    provider: str = ""

    def __init__(self, model: str, *, key_env: str | None, timeout_s: float,
                 max_prompt_tokens: int | None = None):
        self.model = model
        self.key_env = key_env
        self.timeout_s = timeout_s
        self.max_prompt_tokens = max_prompt_tokens

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"

    def available(self) -> bool:
        return self.key_env is None or bool(os.getenv(self.key_env))

    def _api_key(self) -> str:
        return os.getenv(self.key_env or "", "")

    def _err(self, kind: str, msg: str, **kw) -> LLMError:
        return LLMError(kind, msg, provider=self.provider, model=self.model, **kw)

    def _post(self, url: str, headers: dict, body: dict) -> tuple[dict, int]:
        """POST JSON; returns (json, latency_ms) or raises a classified LLMError.
        Error messages include part of the response body but never request headers."""
        t0 = time.perf_counter()
        try:
            r = requests.post(url, headers=headers, json=body,
                              timeout=(CONNECT_TIMEOUT_S, self.timeout_s))
        except requests.Timeout:
            raise self._err("timeout", f"no response within {self.timeout_s:.0f}s")
        except requests.RequestException as e:
            raise self._err("network", type(e).__name__)
        latency = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            retry_after = None
            ra = r.headers.get("retry-after")
            m = _RETRY_DELAY.search(r.text)  # Gemini puts RetryInfo in the body: "retryDelay": "34s"
            try:
                retry_after = float(ra) if ra else float(m.group(1)) if m else None
            except ValueError:
                pass
            body_txt = " ".join(r.text.split())[:300]
            raise self._err(kind_from_status(r.status_code, body_txt), body_txt,
                            status=r.status_code, retry_after=retry_after)
        try:
            return r.json(), latency
        except ValueError:
            raise self._err("bad_response", "response was not JSON")

    def _post_stream(self, url: str, headers: dict, body: dict) -> Iterator[dict]:
        """POST and yield each JSON object from a Server-Sent Events response.
        The read timeout applies between chunks, so a stalled stream still fails over."""
        try:
            r = requests.post(url, headers=headers, json=body, stream=True,
                              timeout=(CONNECT_TIMEOUT_S, self.timeout_s))
        except requests.Timeout:
            raise self._err("timeout", f"no response within {self.timeout_s:.0f}s")
        except requests.RequestException as e:
            raise self._err("network", type(e).__name__)
        with r:
            if r.status_code != 200:
                text = r.text
                m = _RETRY_DELAY.search(text)
                ra = r.headers.get("retry-after")
                try:
                    retry_after = float(ra) if ra else float(m.group(1)) if m else None
                except ValueError:
                    retry_after = None
                body_txt = " ".join(text.split())[:300]
                raise self._err(kind_from_status(r.status_code, body_txt), body_txt,
                                status=r.status_code, retry_after=retry_after)
            # text/event-stream often has no charset, and requests then assumes Latin-1.
            r.encoding = "utf-8"
            try:
                for line in r.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        yield json.loads(data)
                    except ValueError:
                        continue
            except requests.Timeout:
                raise self._err("timeout", f"stream stalled for {self.timeout_s:.0f}s")
            except requests.RequestException as e:
                raise self._err("network", f"stream broke: {type(e).__name__}")

    @abstractmethod
    def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None,
             json_schema: dict | None = None, temperature: float | None = None,
             max_tokens: int | None = None, on_text: TextFn | None = None) -> LLMResponse:
        """One model call. tools and json_schema are optional; raises LLMError.
        With on_text (and no json_schema), streams and calls on_text(piece) as visible text arrives."""
