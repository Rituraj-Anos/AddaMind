"""API keys: one or several per provider, tried in order. A rate-limited key rests for a while and a rejected key is
dropped for the rest of the process, so the next key takes over. Key values are never logged or returned anywhere.

For a variable GEMINI_API_KEY, keys come from GEMINI_API_KEY and from GEMINI_API_KEYS; either may hold several keys
separated by commas. Using several accounts to get around a provider's free-tier limits may break its terms, so use
keys you are allowed to use.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable

import requests

from . import config  # noqa: F401  (loads .env before any key is read)

DEFAULT_REST_S = 60.0
MAX_REST_S = 900.0

_lock = threading.Lock()
_rest_until: dict[tuple[str, int], float] = {}
_rejected: set[tuple[str, int]] = set()


def env_keys(name: str) -> list[str]:
    """Every key configured for `name` (e.g. GEMINI_API_KEY), in order, without duplicates."""
    out: list[str] = []
    for var in (name, name + "S"):
        raw = os.getenv(var) or ""
        for part in raw.replace(";", ",").replace("\n", ",").split(","):
            key = part.strip().strip("\"'")
            if key and key not in out:
                out.append(key)
    return out


def _order(env: str, n: int) -> list[int]:
    """Key positions to try: ready keys first, resting ones after, rejected ones only if nothing else is left."""
    now = time.time()
    with _lock:
        ready = [i for i in range(n) if (env, i) not in _rejected and _rest_until.get((env, i), 0) <= now]
        resting = [i for i in range(n) if (env, i) not in _rejected and i not in ready]
        return ready + resting or list(range(n))


def request_with_keys(env: str, send: Callable[[str], requests.Response]) -> requests.Response:
    """Call `send(key)` with each key in turn until one is not rate limited or rejected. Returns the last response.
    With no key configured, `send("")` runs once so the caller reports the missing key the way it always did."""
    keys = env_keys(env)
    if not keys:
        return send("")
    last: requests.Response | None = None
    for i in _order(env, len(keys)):
        last = r = send(keys[i])
        if r.status_code == 429:
            try:
                rest = min(float(r.headers.get("retry-after") or DEFAULT_REST_S), MAX_REST_S)
            except ValueError:
                rest = DEFAULT_REST_S
            with _lock:
                _rest_until[(env, i)] = time.time() + rest
        elif r.status_code in (401, 403) or (r.status_code == 400 and "API key" in r.text[:300]):
            with _lock:
                _rejected.add((env, i))
        else:
            return r
    assert last is not None
    return last


def status(env: str) -> dict:
    """How many keys are configured, ready, resting or rejected. Counts only."""
    n = len(env_keys(env))
    now = time.time()
    with _lock:
        rejected = sum(1 for i in range(n) if (env, i) in _rejected)
        resting = sum(1 for i in range(n) if (env, i) not in _rejected and _rest_until.get((env, i), 0) > now)
    return {"configured": n, "ready": n - rejected - resting, "resting": resting, "rejected": rejected}


def reset() -> None:
    """Forget every rest and rejection (used by tests)."""
    with _lock:
        _rest_until.clear()
        _rejected.clear()
