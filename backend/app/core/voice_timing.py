"""Optional per-turn timers for the voice path.

No-ops unless a voice turn calls begin(). Does not call any model.
"""

from __future__ import annotations

import contextvars
import time

_clock: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "voice_turn_clock", default=None
)


def begin() -> None:
    _clock.set({"t0": time.perf_counter(), "marks": {}})


def ensure() -> None:
    """Start a clock only when this context does not already have one.

    A worker thread inherits the caller's clock. Calling ensure() there
    must not replace it, or later TTS marks would be invisible.
    """
    if _clock.get() is None:
        begin()


def mark(name: str) -> None:
    clock = _clock.get()
    if not clock:
        return
    clock["marks"][name] = int((time.perf_counter() - clock["t0"]) * 1000)


def snapshot() -> dict[str, int]:
    clock = _clock.get()
    if not clock:
        return {}
    return dict(clock["marks"])
