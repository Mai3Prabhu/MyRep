"""Per-request correlation id for structured logs. No secrets."""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "myrep_request_id", default=None
)


def get_request_id() -> str:
    return _request_id.get() or "-"


def bind_request_id(request_id: str | None = None) -> contextvars.Token:
    return _request_id.set(request_id or str(uuid.uuid4()))


def reset_request_id(token: contextvars.Token) -> None:
    _request_id.reset(token)


@contextmanager
def request_scope(request_id: str | None = None) -> Iterator[str]:
    token = bind_request_id(request_id)
    try:
        yield get_request_id()
    finally:
        reset_request_id(token)
