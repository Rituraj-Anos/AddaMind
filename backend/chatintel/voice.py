"""Spoken roasts (extra e): Gemini text-to-speech, cached on disk by text and voice. The browser's own
voice is the fallback, so a failure here is never fatal."""
from __future__ import annotations

import base64
import hashlib
import re
import struct

import requests

from backend.core.config import env_str
from backend.core.keys import request_with_keys

from . import db

MODEL = env_str("ADDAMIND_TTS_MODEL", "gemini-3.8-flash-lite-tts")
VOICE = env_str("ADDAMIND_TTS_VOICE", "Puck")
MAX_CHARS = 400


class VoiceError(Exception):
    pass


def _wav(pcm: bytes, rate: int) -> bytes:
    """16-bit mono PCM in a WAV container, for when the API returns raw audio/L16."""
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm)


def speak(text: str) -> bytes:
    text = " ".join((text or "").split())[:MAX_CHARS]
    if not text:
        raise ValueError("nothing to say")
    path = db.data_dir() / "tts" / f"{hashlib.sha1(f'{MODEL}|{VOICE}|{text}'.encode()).hexdigest()}.wav"
    if path.exists():
        return path.read_bytes()
    try:
        r = request_with_keys("GEMINI_API_KEY", lambda key: requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            headers={"x-goog-api-key": key},
            json={"contents": [{"parts": [{"text": f"Say this playfully, like a friend roasting a friend: {text}"}]}],
                  "generationConfig": {"responseModalities": ["AUDIO"],
                                       "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}},
            timeout=(5, 45)))
    except requests.RequestException as e:
        raise VoiceError(type(e).__name__) from None
    if not r.ok:
        raise VoiceError(f"HTTP {r.status_code}")
    try:
        part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        audio = base64.b64decode(part["data"])
    except (KeyError, IndexError, ValueError):
        raise VoiceError("no audio in the response") from None
    mime = part.get("mimeType", "")
    if not mime.startswith("audio/wav"):
        rate = int(m.group(1)) if (m := re.search(r"rate=(\d+)", mime)) else 24000
        audio = _wav(audio, rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return audio
