"""Typed LangGraph state. No secrets, no full DB models, no raw documents."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


Intent = Literal["knowledge", "contact", "unsupported"]


class AgentState(TypedDict, total=False):
    # Set by the API from the authorized path parameter — never by the model.
    profile_id: str
    question: str
    conversation_history: list[dict[str, str]]
    profile_name: str

    intent: Intent
    evidence_status: str
    retrieved_chunks: list[dict[str, Any]]
    # Facts typed into the profile form. Used when documents do not cover the question.
    profile_facts: str
    # Set when document search already proved the model key is rejected.
    model_unavailable: bool
    answer: str
    source_references: list[dict[str, Any]]
    contact_status: str
    error: str
    # "text" (default) or "voice" — does not change evidence rules.
    channel: str
    # Layer 7 — retrieval-only rewrite of the user question. Never replaces `question`.
    retrieval_query: str
    query_rewritten: bool
    # Layer 8 — log correlation only. Never used for retrieval or generation.
    request_id: str
