"""Patch LangGraph's Reviver before any test module imports langgraph."""

from app.agent import compat as _langgraph_compat  # noqa: F401
