"""Error classification so the router can decide: skip, cool down, or give up."""
from __future__ import annotations

# kind -> meaning
#   auth          key missing/invalid: skip the whole provider for this process
#   not_found     model retired or not enabled for this key: skip the model for a long time
#   rate_limit    429: cool down (Retry-After if given)
#   overloaded    5xx / high demand: cool down with exponential backoff
#   timeout       no response in time: cool down with exponential backoff
#   network       connection failure
#   bad_request   400: our payload was rejected by this model
#   bad_response  2xx but unusable (empty, blocked, malformed tool call)
KINDS = {"auth", "not_found", "rate_limit", "overloaded", "timeout", "network", "bad_request", "bad_response"}


class LLMError(Exception):
    def __init__(self, kind: str, message: str, *, status: int | None = None,
                 retry_after: float | None = None, provider: str = "", model: str = ""):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.retry_after = retry_after
        self.provider = provider
        self.model = model

    def short(self) -> str:
        code = f" {self.status}" if self.status else ""
        return f"{self.kind}{code}: {str(self)[:160]}"


class AllModelsFailed(Exception):
    def __init__(self, errors: list[LLMError]):
        self.errors = errors
        summary = "; ".join(f"{e.provider}:{e.model} -> {e.kind}" for e in errors) or "no models available"
        super().__init__(f"All models failed ({summary})")


def kind_from_status(status: int, body: str = "") -> str:
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limit"
    if status in (408, 504):
        return "timeout"
    if status >= 500:
        return "overloaded"
    if status == 400 and "API key" in body:
        return "auth"
    return "bad_request"
