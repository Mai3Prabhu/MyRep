"""LangGraph/langchain-core compatibility shims.

LangGraph constructs `Reviver()` at import time in JsonPlusSerializer.
The pending deprecation fires when `allowed_objects` is omitted.
Patch the original class in place so already-bound imports are covered.
"""

from __future__ import annotations

from langchain_core.load.load import Reviver

_orig_init = Reviver.__init__
if getattr(Reviver, "_myrep_allowed_objects_patched", False) is False:

    def _patched_init(self, *args, **kwargs):
        if "allowed_objects" not in kwargs:
            kwargs["allowed_objects"] = "core"
        return _orig_init(self, *args, **kwargs)

    Reviver.__init__ = _patched_init  # type: ignore[method-assign]
    Reviver._myrep_allowed_objects_patched = True  # type: ignore[attr-defined]
