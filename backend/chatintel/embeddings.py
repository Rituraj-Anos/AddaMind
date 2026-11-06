"""Text embeddings: NVIDIA first, Gemini as fallback, cached in llm_cache by model and text hash.

Vectors from different models can't be compared, so callers keep the model name next to each vector.
ADDAMIND_EMBEDDINGS=off disables network calls (tests, offline); search then runs on keywords only.
"""
from __future__ import annotations

import base64
import hashlib
import logging

import numpy as np
import requests

from backend.core.config import env_str
from backend.core.keys import request_with_keys

from . import db

log = logging.getLogger("addamind.embeddings")

GEMINI = "gemini-embedding-001"
NVIDIA = "nvidia/nemotron-3-embed-1b"
# NVIDIA first: Gemini's free tier counts each text in a batch as a request (~100 a minute), so a
# 500-passage chat would always hit 429 there.
MODELS = (NVIDIA, GEMINI)
BATCH = 100  # Gemini's batchEmbedContents limit


class EmbeddingError(Exception):
    pass


def enabled() -> bool:
    return env_str("ADDAMIND_EMBEDDINGS", "on").lower() not in ("off", "0", "false", "no")


def _gemini(texts: list[str], query: bool) -> list[list[float]]:
    task = "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT"
    body = {"requests": [{"model": f"models/{GEMINI}", "content": {"parts": [{"text": t}]}, "taskType": task,
                          "outputDimensionality": 768} for t in texts]}
    # No wait on 429: another key takes over, or the next embedding model answers at once.
    r = request_with_keys("GEMINI_API_KEY", lambda key: requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI}:batchEmbedContents",
        headers={"x-goog-api-key": key}, json=body, timeout=(5, 60)))
    if not r.ok:
        raise EmbeddingError(f"gemini {r.status_code}")
    return [e["values"] for e in r.json()["embeddings"]]


def _nvidia(texts: list[str], query: bool) -> list[list[float]]:
    r = request_with_keys("NVIDIA_API_KEY", lambda key: requests.post(
        "https://integrate.api.nvidia.com/v1/embeddings", headers={"Authorization": f"Bearer {key}"},
        json={"model": NVIDIA, "input": texts, "input_type": "query" if query else "passage",
              "encoding_format": "float", "truncate": "END"}, timeout=(5, 60)))
    if not r.ok:
        raise EmbeddingError(f"nvidia {r.status_code}")
    return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]


_CALL = {GEMINI: _gemini, NVIDIA: _nvidia}


def _key(model: str, query: bool, text: str) -> str:
    return f"emb:{model}:{'q' if query else 'd'}:{hashlib.sha1(text.encode()).hexdigest()}"


def _unit(v) -> np.ndarray:
    a = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(a))
    return a / n if n else a


def to_blob(v: np.ndarray) -> bytes:
    return v.astype(np.float32).tobytes()


def from_blob(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)


def embed(texts: list[str], model: str, query: bool = False) -> list[np.ndarray]:
    """Unit vectors for `texts` from one model, using the cache. Raises EmbeddingError on failure."""
    if not enabled():
        raise EmbeddingError("embeddings are turned off")
    keys = [_key(model, query, t) for t in texts]
    with db.connect() as con:
        cached = {}
        for i in range(0, len(keys), 500):
            part = keys[i:i + 500]
            cached.update(con.execute(f"SELECT key, value FROM llm_cache WHERE key IN ({','.join('?' * len(part))})",
                                      part).fetchall())
    out: dict[int, np.ndarray] = {i: from_blob(base64.b64decode(cached[k])) for i, k in enumerate(keys) if k in cached}
    todo = [i for i in range(len(texts)) if i not in out]
    for s in range(0, len(todo), BATCH):
        idx = todo[s:s + BATCH]
        try:
            vecs = _CALL[model]([texts[i] for i in idx], query)
        except requests.RequestException as e:
            raise EmbeddingError(f"{model}: {type(e).__name__}") from None
        rows = []
        for i, v in zip(idx, vecs):
            out[i] = _unit(v)
            rows.append((keys[i], base64.b64encode(to_blob(out[i])).decode()))
        with db.connect() as con:
            con.executemany("INSERT OR REPLACE INTO llm_cache(key, value) VALUES (?, ?)", rows)
    return [out[i] for i in range(len(texts))]


def embed_documents(texts: list[str], on_batch=None, models: tuple[str, ...] = MODELS) -> list[tuple[str, np.ndarray] | None]:
    """(model, vector) for each text, all from one model so they rank together. If a model fails on any
    batch the whole set moves to the next model (finished batches stay cached for a later retry).
    All None if every model failed: search then uses keywords."""
    if not enabled() or not texts:
        return [None] * len(texts)
    for model in models:
        try:
            vecs = []
            for s in range(0, len(texts), BATCH):
                vecs += embed(texts[s:s + BATCH], model)
                if on_batch:
                    on_batch(min(s + BATCH, len(texts)), len(texts))
            return [(model, v) for v in vecs]
        except EmbeddingError as e:
            log.warning("embeddings fell back from %s: %s", model, e)
    return [None] * len(texts)
