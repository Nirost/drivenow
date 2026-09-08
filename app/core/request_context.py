"""
Request-scoped correlation ID.

A ContextVar rather than a global, so concurrent requests never read each
other's ID. The logging filter reads from here, which is what lets a
single request be traced across API, service, and repository log lines.
"""
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return request_id_var.get()


def set_request_id(value: str) -> None:
    request_id_var.set(value)
