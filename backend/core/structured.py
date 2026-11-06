"""Structured output: get a Pydantic-validated object back from any provider in the chain.

    from pydantic import BaseModel
    from backend.core.structured import structured

    class Triage(BaseModel):
        category: Literal["bug", "billing", "other"]
        urgency: int  # 1-5
        summary: str

    result = structured("Customer says: app charges me twice", Triage)   # -> Triage instance

Providers get a JSON Schema (Gemini: responseJsonSchema; OpenAI-compatible: response_format,
with a json_object fallback). The reply is validated with Pydantic and retried once with the
validation error if it doesn't fit.
"""
from __future__ import annotations

import copy
import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .llm import LLMRouter, Message, get_router

T = TypeVar("T", bound=BaseModel)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def inline_schema(model: type[BaseModel]) -> dict:
    """Pydantic JSON Schema with $defs/$ref inlined and titles dropped: the form every provider accepts."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node, depth=0, in_properties=False):
        if depth > 20:
            raise ValueError("schema is too deeply nested or recursive")
        if isinstance(node, dict):
            if "$ref" in node and not in_properties:
                target = copy.deepcopy(defs[node["$ref"].split("/")[-1]])
                rest = {k: v for k, v in node.items() if k != "$ref"}
                return resolve({**target, **rest}, depth + 1)
            # Inside "properties" the keys are field names: a field called "title" must stay.
            return {k: resolve(v, depth + 1, k == "properties" and not in_properties)
                    for k, v in node.items() if in_properties or k != "title"}
        if isinstance(node, list):
            return [resolve(v, depth + 1) for v in node]
        return node

    return resolve(schema)


def parse_json(text: str):
    """Model output -> Python object. Tolerates code fences and prose around one JSON object."""
    t = _FENCE.sub("", text.strip())
    try:
        return json.loads(t)
    except ValueError:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            return json.loads(t[start:end + 1])
        raise


def structured(prompt: str | list[Message], schema: type[T], *, system: str | None = None,
               router: LLMRouter | None = None, on_event=None, retries: int = 1) -> T:
    """One LLM call (plus up to `retries` repairs) returning a validated `schema` instance."""
    router = router or get_router()
    msgs = [Message("user", prompt)] if isinstance(prompt, str) else list(prompt)
    if system:
        msgs.insert(0, Message("system", system))
    json_schema = inline_schema(schema)
    last_error = ""
    for attempt in range(retries + 1):
        resp = router.chat(msgs, json_schema=json_schema, temperature=0, on_event=on_event)
        try:
            return schema.model_validate(parse_json(resp.text))
        except (ValueError, ValidationError) as e:
            last_error = str(e)[:800]
            msgs = msgs + [Message("assistant", resp.text),
                           Message("user", "That JSON did not match the schema. Error:\n" + last_error +
                                   "\nReply with only the corrected JSON object.")]
    raise ValueError(f"model output did not match {schema.__name__}: {last_error}")
