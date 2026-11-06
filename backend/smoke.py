"""Pre-demo health check for every model in LLM_CHAIN. Prints no secrets.

    python -m backend.smoke            # every model: tool round trip + JSON output
    python -m backend.smoke --switch   # also: continue a Gemini tool conversation on Groq and vice versa
"""
from __future__ import annotations

import json
import sys
import time

from backend.core.config import env_str
from backend.core.llm import LLMError, Message, ToolSpec, build_chain
from backend.core.llm.router import DEFAULT_CHAIN

WEATHER = ToolSpec("get_weather", "Get current weather for a city",
                   {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]})
SCHEMA = {"type": "object", "properties": {"sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                                           "score": {"type": "number"}}, "required": ["sentiment", "score"]}
Q = [Message("system", "Use tools when helpful."), Message("user", "What's the weather in Kolkata?")]


def tool_round_trip(first, second=None):
    """first makes the tool call; second (or first) must answer using the tool result."""
    r1 = first.chat(Q, [WEATHER])
    if not r1.tool_calls:
        return f"no tool call (text: {r1.text[:60]!r})", None
    tc = r1.tool_calls[0]
    hist = Q + [r1.to_message(),
                Message("tool", json.dumps({"city": tc.args.get("city"), "temp_c": 29, "condition": "light rain"}),
                        tool_call_id=tc.id, name=tc.name)]
    r2 = (second or first).chat(hist, [WEATHER])
    ok = "29" in r2.text
    return f"{'OK ' if ok else 'ANSWER MISSING 29 '}{r1.latency_ms + r2.latency_ms}ms -> {r2.text[:70]!r}", ok


def json_output(p):
    r = p.chat([Message("user", "Classify the sentiment: 'The demo went brilliantly!'")], json_schema=SCHEMA)
    data = json.loads(r.text)
    assert data["sentiment"] in ("positive", "negative", "neutral")
    return f"OK {r.latency_ms}ms {data}"


def run(label, fn):
    t = time.perf_counter()
    try:
        out = fn()
        out = out[0] if isinstance(out, tuple) else out
    except LLMError as e:
        out = f"FAIL {e.short()}"
    except Exception as e:  # noqa: BLE001 - report anything
        out = f"FAIL {type(e).__name__}: {str(e)[:120]}"
    print(f"  {label:<10} {out}  [{time.perf_counter() - t:.1f}s]", flush=True)


def main():
    chain = build_chain(env_str("LLM_CHAIN") or DEFAULT_CHAIN)  # one entry per model and API key
    for p in chain:
        print(p.key, "" if p.available() else "(no API key, skipped)", flush=True)
        if p.available():
            run("tools", lambda p=p: tool_round_trip(p))
            run("json", lambda p=p: json_output(p))

    if "--switch" in sys.argv:
        gem = next((p for p in chain if p.provider == "gemini"), None)
        oai = next((p for p in chain if p.provider in ("groq", "nvidia")), None)
        if gem and oai:
            for g in [p for p in chain if p.provider == "gemini"]:  # first Gemini model that responds
                try:
                    g.chat([Message("user", "hi")]); gem = g; break
                except LLMError:
                    continue
            print(f"provider switch ({gem.key} <-> {oai.key})")
            run("gem->oai", lambda: tool_round_trip(gem, oai))
            run("oai->gem", lambda: tool_round_trip(oai, gem))


if __name__ == "__main__":
    main()
