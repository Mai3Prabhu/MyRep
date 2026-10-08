"""LangGraph node functions. Orchestrate existing services; do not retrieve from Qdrant directly."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import HTTPException
from langchain_core.runnables import RunnableConfig

from app.agent.state import AgentState
from app.agent import intent as intent_module
from app.agent.tools import make_create_contact_request_tool
from app.core import voice_timing
from app.core.request_context import get_request_id
from app.schemas.rag import ConversationTurn, EvidenceStatus
from app.schemas.retrieval import RetrievedChunk
from app.services import (
    contact_service,
    generation_service,
    profile_service,
    query_rewrite_service,
    rag_service,
)
from app.services.evidence_service import EvidenceState

logger = logging.getLogger(__name__)

_UNSUPPORTED_ANSWER = (
    "I can't help with that. I represent professional background only — "
    "I don't discuss salary, negotiate, make commitments, or share private contact details."
)


def _db(config: RunnableConfig):
    return config["configurable"]["db"]


def _profile_id(state: AgentState) -> uuid.UUID:
    return uuid.UUID(state["profile_id"])


def _history(state: AgentState) -> list[ConversationTurn]:
    raw = state.get("conversation_history") or []
    turns: list[ConversationTurn] = []
    for item in raw:
        try:
            turns.append(ConversationTurn(role=item["role"], content=item["content"]))
        except Exception:
            continue
    return rag_service.bound_conversation_history(turns)


def classify_intent(state: AgentState, config: RunnableConfig) -> dict:
    started = time.perf_counter()
    voice_timing.mark("intent_start")
    # First voice turn: rules already catch contact and unsupported.
    # Skipping the Gemini classifier avoids a round trip before retrieval.
    # Later turns still use the classifier so a short "Yes." can confirm contact.
    if (state.get("channel") or "text") == "voice" and not state.get("conversation_history"):
        intent = intent_module.classify_with_rules(state["question"]) or "knowledge"
    else:
        intent = intent_module.classify_intent(state["question"])
    logger.info(
        "intent_classified request_id=%s profile_id=%s intent=%s channel=%s latency_ms=%d",
        state.get("request_id") or get_request_id(),
        state["profile_id"],
        intent,
        state.get("channel") or "text",
        int((time.perf_counter() - started) * 1000),
    )
    voice_timing.mark("intent_end")
    return {"intent": intent}


def rewrite_query(state: AgentState, config: RunnableConfig) -> dict:
    """Knowledge-only. Resolves follow-ups for retrieval; does not change profile_id."""
    history = _history(state)
    result = query_rewrite_service.rewrite_for_retrieval(
        question=state["question"],
        conversation_history=history,
    )
    logger.info(
        "query_rewrite_applied request_id=%s profile_id=%s rewritten=%s "
        "history_count=%d query_len=%d",
        state.get("request_id") or get_request_id(),
        state["profile_id"],
        result.was_rewritten,
        len(history),
        len(result.retrieval_query),
    )
    return {
        "retrieval_query": result.retrieval_query,
        "query_rewritten": result.was_rewritten,
    }


def retrieve_knowledge(state: AgentState, config: RunnableConfig) -> dict:
    db = _db(config)
    profile_id = _profile_id(state)
    retrieval_query = (state.get("retrieval_query") or state["question"]).strip()
    profile = profile_service.get_profile(db, profile_id)
    profile_facts = profile_service.format_saved_profile(profile)
    model_unavailable = False
    try:
        ev_state, chunks = rag_service.retrieve_evidence(
            db=db,
            profile_id=profile_id,
            question=retrieval_query,
        )
    except HTTPException as exc:
        # Document search can fail (embedding or vector store) while the form
        # fields still have the answer. Keep going with those saved facts.
        detail = str(exc.detail)
        model_unavailable = "UNAUTHENTICATED" in detail or "401" in detail
        logger.warning(
            "document_retrieval_failed request_id=%s profile_id=%s status=%s detail=%s",
            state.get("request_id") or get_request_id(),
            profile_id,
            exc.status_code,
            exc.detail,
        )
        ev_state, chunks = EvidenceState.NO_EVIDENCE, []
    if profile_facts and ev_state != EvidenceState.EVIDENCE_AVAILABLE:
        ev_state = EvidenceState.EVIDENCE_AVAILABLE
    serialized = [
        {
            "document_id": str(c.document_id),
            "filename": c.filename,
            "page_number": c.page_number,
            "chunk_index": c.chunk_index,
            "text": c.text,
            "score": c.score,
        }
        for c in chunks
    ]
    logger.info(
        "evidence_assessed request_id=%s profile_id=%s state=%s chunks=%d",
        state.get("request_id") or get_request_id(),
        profile_id,
        ev_state.value,
        len(serialized),
    )
    return {
        "evidence_status": ev_state.value,
        "retrieved_chunks": serialized,
        "profile_facts": profile_facts,
        "model_unavailable": model_unavailable,
    }


_VOICE_INSUFFICIENT = (
    "I don't have enough information in the profile to answer that."
)
_VOICE_UNSUPPORTED = (
    "I can't help with that. I only cover professional background — "
    "not salary, negotiation, or private details."
)


def _channel(state: AgentState) -> str:
    return state.get("channel") or "text"


def generate_answer(state: AgentState, config: RunnableConfig) -> dict:
    chunks = [
        RetrievedChunk(
            document_id=uuid.UUID(item["document_id"]),
            filename=item["filename"],
            page_number=item["page_number"],
            chunk_index=item["chunk_index"],
            text=item["text"],
            score=float(item["score"]),
        )
        for item in (state.get("retrieved_chunks") or [])
    ]
    configurable = config.get("configurable") or {}
    sentence_queue = configurable.get("sentence_queue")
    cancel = configurable.get("cancel_event")
    facts = state.get("profile_facts") or ""
    if state.get("model_unavailable"):
        fallback = profile_service.answer_from_saved_profile(state["question"], facts)
        if fallback:
            answer = fallback
        else:
            raise HTTPException(
                status_code=401,
                detail=(
                    "The language model key was rejected. "
                    "Update GEMINI_API_KEY in the backend .env file and restart the server."
                ),
            )
    else:
        try:
            if _channel(state) == "voice" and sentence_queue is not None:
                parts: list[str] = []
                for sentence in generation_service.iter_spoken_sentences(
                    question=state["question"],
                    evidence=chunks,
                    conversation_history=_history(state),
                    channel="voice",
                    profile_facts=facts,
                    should_stop=lambda: bool(cancel is not None and cancel.is_set()),
                ):
                    if cancel is not None and cancel.is_set():
                        break
                    sentence_queue.put(sentence)
                    parts.append(sentence)
                answer = " ".join(parts).strip()
            else:
                answer = rag_service.generate_grounded_answer(
                    question=state["question"],
                    chunks=chunks,
                    conversation_history=_history(state),
                    channel=_channel(state),
                    profile_facts=facts,
                )
        except HTTPException as exc:
            fallback = profile_service.answer_from_saved_profile(state["question"], facts)
            if not fallback:
                raise
            logger.warning(
                "generation_used_saved_profile request_id=%s profile_id=%s status=%s",
                state.get("request_id") or get_request_id(),
                state["profile_id"],
                exc.status_code,
            )
            answer = fallback
    sources = [
        {
            "document_id": str(s.document_id),
            "filename": s.filename,
            "page_number": s.page_number,
            "chunk_index": s.chunk_index,
            "score": s.score,
            "excerpt": s.excerpt,
        }
        for s in rag_service.sources_from_chunks(chunks, state["question"], answer)
    ]
    logger.info(
        "agent_request_completed request_id=%s profile_id=%s path=answer "
        "evidence_status=%s success=true",
        state.get("request_id") or get_request_id(),
        state["profile_id"],
        EvidenceStatus.EVIDENCE_AVAILABLE.value,
    )
    return {
        "answer": answer,
        "source_references": sources,
        "evidence_status": EvidenceStatus.EVIDENCE_AVAILABLE.value,
    }


def clarify(state: AgentState, config: RunnableConfig) -> dict:
    status = state.get("evidence_status") or EvidenceState.NO_EVIDENCE.value
    if status == EvidenceState.WEAK_EVIDENCE.value:
        evidence = EvidenceStatus.WEAK_EVIDENCE
    else:
        evidence = EvidenceStatus.NO_EVIDENCE
    resp = rag_service.insufficient_response(state["question"], evidence)
    answer = (
        _VOICE_INSUFFICIENT if _channel(state) == "voice" else resp.answer
    )
    logger.info(
        "agent_request_completed request_id=%s profile_id=%s path=clarify "
        "evidence_status=%s success=true",
        state.get("request_id") or get_request_id(),
        state["profile_id"],
        resp.evidence_status.value,
    )
    return {
        "answer": answer,
        "source_references": [],
        "evidence_status": resp.evidence_status.value,
    }


def handle_unsupported(state: AgentState, config: RunnableConfig) -> dict:
    logger.info(
        "agent_request_completed request_id=%s profile_id=%s path=unsupported "
        "intent=unsupported success=true",
        state.get("request_id") or get_request_id(),
        state["profile_id"],
    )
    answer = _VOICE_UNSUPPORTED if _channel(state) == "voice" else _UNSUPPORTED_ANSWER
    return {
        "answer": answer,
        "source_references": [],
        "evidence_status": EvidenceStatus.NO_EVIDENCE.value,
        "contact_status": "none",
    }


def route_contact(state: AgentState, config: RunnableConfig) -> dict:
    db = _db(config)
    profile_id = _profile_id(state)
    profile = profile_service.get_profile(db, profile_id)
    logger.info(
        "contact_requested request_id=%s profile_id=%s",
        state.get("request_id") or get_request_id(),
        profile_id,
    )

    public_methods = contact_service.extract_public_contact_methods(
        profile.contact_preferences
    )
    history = _history(state)
    confirmed = contact_service.visitor_confirmed_contact(state["question"], history)

    action = None
    if confirmed and public_methods:
        tool = make_create_contact_request_tool(db, profile_id)
        action = tool.invoke({"visitor_message": state["question"][:4000]})

    answer, contact_status = contact_service.format_contact_answer(
        profile_name=profile.name,
        public_methods=public_methods,
        confirmed=confirmed,
        action=action,
        spoken=_channel(state) == "voice",
    )
    logger.info(
        "agent_request_completed request_id=%s profile_id=%s path=contact "
        "contact_status=%s success=true",
        state.get("request_id") or get_request_id(),
        profile_id,
        contact_status,
    )
    return {
        "answer": answer,
        "source_references": [],
        "evidence_status": EvidenceStatus.NO_EVIDENCE.value,
        "contact_status": contact_status,
        "profile_name": profile.name,
    }
