"""Provider-neutral message types. Providers convert to/from their own wire formats."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


def new_call_id() -> str:
    return "call_" + uuid.uuid4().hex[:12]


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class Message:
    role: Role
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # role == "tool": which call this answers
    name: str | None = None  # role == "tool": tool name
    # Provider-specific data needed to continue the conversation on the same provider,
    # e.g. Gemini's raw parts with thought signatures. Other providers ignore it.
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        d = dict(d)
        d["tool_calls"] = [ToolCall(**tc) for tc in d.get("tool_calls") or []]
        return cls(**d)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema, type "object"


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    provider: str
    model: str
    latency_ms: int
    usage: dict = field(default_factory=dict)  # input_tokens / output_tokens when reported
    meta: dict = field(default_factory=dict)

    def to_message(self) -> Message:
        return Message(role="assistant", text=self.text, tool_calls=self.tool_calls, meta=self.meta)
