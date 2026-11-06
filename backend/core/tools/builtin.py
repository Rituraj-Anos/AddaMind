"""General-purpose tools available to every agent profile."""
from __future__ import annotations

import ast
import math
import operator
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .registry import tool

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"sqrt": math.sqrt, "log": math.log, "log10": math.log10, "exp": math.exp, "abs": abs,
          "round": round, "min": min, "max": max, "sin": math.sin, "cos": math.cos, "tan": math.tan}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError(f"unsupported expression element: {ast.dump(node)[:40]}")


@tool
def calculate(expression: Annotated[str, "Math expression, e.g. '23*47 + 100' or 'sqrt(2)*pi'"]) -> dict:
    """Evaluate a math expression exactly. Use this for any arithmetic instead of computing mentally."""
    if len(expression) > 300:
        raise ValueError("expression too long")
    return {"expression": expression, "result": _eval(ast.parse(expression, mode="eval").body)}


@tool
def get_current_datetime(timezone: Annotated[str, "IANA timezone, e.g. 'Asia/Kolkata'"] = "Asia/Kolkata") -> dict:
    """Get the current date, time and weekday in a timezone."""
    try:
        now = datetime.now(ZoneInfo(timezone))
    except ZoneInfoNotFoundError:
        raise ValueError(f"unknown timezone '{timezone}'")
    return {"timezone": timezone, "iso": now.isoformat(timespec="seconds"), "weekday": now.strftime("%A")}


@tool
def get_weather(city: Annotated[str, "City name"]) -> dict:
    """Get current weather for a city. (Demo tool returning mock data.)"""
    return {"city": city, "temp_c": 29, "condition": "humid, light rain", "source": "mock"}
