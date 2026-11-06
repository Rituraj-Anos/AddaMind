"""Tool registry: decorate a typed Python function and it becomes an LLM tool.

    from backend.core.tools import tool

    @tool
    def get_stock_price(ticker: Annotated[str, "Ticker symbol, e.g. AAPL"], days: int = 1) -> dict:
        '''Get recent closing prices for a stock.'''
        ...

The JSON Schema comes from the type hints (via Pydantic), the description from the docstring.
Arguments from the model are validated/coerced before the call. Errors are returned to the
model as {"error": ...} so it can correct itself instead of crashing the run.
"""
from __future__ import annotations

import inspect
import json
import time
from dataclasses import dataclass
from typing import Annotated, Any, Callable, get_args, get_origin

from pydantic import BaseModel, Field, ValidationError, create_model

from ..llm.types import ToolSpec

MAX_RESULT_CHARS = 12000  # what the model sees; keeps prompts inside small-TPM limits


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[..., Any]
    args_model: type[BaseModel]

    @property
    def spec(self) -> ToolSpec:
        schema = self.args_model.model_json_schema()
        return ToolSpec(self.name, self.description, _clean(schema))


def _clean(schema: dict) -> dict:
    """Drop Pydantic 'title' noise; keep the schema minimal for every provider."""
    if isinstance(schema, dict):
        return {k: _clean(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_clean(v) for v in schema]
    return schema


def _args_model(func: Callable) -> type[BaseModel]:
    fields = {}
    # eval_str: resolve string annotations from `from __future__ import annotations`
    for pname, p in inspect.signature(func, eval_str=True).parameters.items():
        ann = p.annotation if p.annotation is not inspect.Parameter.empty else str
        default = ... if p.default is inspect.Parameter.empty else p.default
        if get_origin(ann) is Annotated:  # Annotated[str, "description"]
            base, *extra = get_args(ann)
            desc = next((x for x in extra if isinstance(x, str)), None)
            ann = base
            default = Field(default, description=desc) if desc else default
        fields[pname] = (ann, default)
    return create_model(f"{func.__name__}_args", **fields)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def tool(self, func: Callable | None = None, *, name: str | None = None, description: str | None = None):
        def register(f: Callable) -> Callable:
            desc = description or inspect.getdoc(f) or f.__name__.replace("_", " ")
            t = Tool(name or f.__name__, desc.strip(), f, _args_model(f))
            self._tools[t.name] = t
            return f
        return register(func) if func else register

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self, names: list[str] | None = None) -> list[ToolSpec]:
        return [t.spec for n, t in self._tools.items() if names is None or n in names]

    def execute(self, name: str, args: dict, allowed: list[str] | None = None) -> tuple[bool, Any, int]:
        """Run a tool. Returns (ok, result, duration_ms); never raises."""
        t0 = time.perf_counter()
        ms = lambda: int((time.perf_counter() - t0) * 1000)  # noqa: E731
        t = self._tools.get(name)
        if t is None or (allowed is not None and name not in allowed):
            avail = allowed if allowed is not None else self.names()
            return False, {"error": f"Unknown tool '{name}'. Available: {', '.join(avail)}"}, ms()
        try:
            parsed = t.args_model.model_validate(args or {})
        except ValidationError as e:
            errs = "; ".join(f"{'.'.join(map(str, er['loc']))}: {er['msg']}" for er in e.errors())
            return False, {"error": f"Invalid arguments: {errs}"}, ms()
        try:
            result = t.func(**{k: getattr(parsed, k) for k in t.args_model.model_fields})
        except Exception as e:  # noqa: BLE001 - tool failures are reported to the model
            return False, {"error": f"{type(e).__name__}: {e}"}, ms()
        return True, result, ms()


def result_to_text(result: Any) -> str:
    if isinstance(result, BaseModel):
        result = result.model_dump()
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + f"... [truncated {len(text) - MAX_RESULT_CHARS} chars]"
    return text


registry = ToolRegistry()
tool = registry.tool
