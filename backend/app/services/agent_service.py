"""
agent_service.py — API-facing entry to the LangGraph representative.

Authorization/visibility stays in the API layer. This service receives an
already-authorized profile_id from the path parameter.
"""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy.orm import Session

from app.agent.graph import get_graph
from app.core.request_context import request_scope
from app.schemas.rag import (
    AskResponse,
    ConversationTurn,
    EvidenceStatus,
    SourceReference,
    TurnSummary,
)
from app.services import conversation_summary_service, profile_service, rag_service

logger = logging.getLogger(__name__)


def _turn_summary(profile, question: str, answer: str, intent, evidence_status) -> TurnSummary | None:
    """Deterministic digest for the summary UI. Never fails the request."""
    try:
        entities, technologies = conversation_summary_service.build_vocabulary(
            projects=getattr(profile, "projects", None),
            experience=getattr(profile, "experience", None),
            education=getattr(profile, "education", None),
            skills=getattr(profile, "skills", None),
        )
        return conversation_summary_service.build_turn_summary(
            question=question,
            answer=answer,
            intent=intent,
            evidence_status=evidence_status,
            entity_vocabulary=entities,
            technology_vocabulary=technologies,
            exclude=[getattr(profile, "name", "") or ""],
        )
    except Exception as exc:
        logger.warning("turn_summary_failed error_type=%s", type(exc).__name__)
        return None


def handle_question(
    db: Session,
    profile_id: uuid.UUID,
    question: str,
    conversation_history: list[ConversationTurn] | None = None,
    channel: str = "text",
    sentence_queue=None,
    cancel_event=None,
) -> AskResponse:
    # Validate the profile exists before graph work. Isolation uses this id only.
    profile = profile_service.get_profile(db, profile_id)

    bounded = rag_service.bound_conversation_history(conversation_history)
    history_dicts = [{"role": t.role, "content": t.content} for t in bounded]
    safe_channel = "voice" if channel == "voice" else "text"

    with request_scope() as request_id:
        started = time.perf_counter()
        error_type = None
        logger.info(
            "agent_request_started request_id=%s profile_id=%s question_len=%d "
            "history_turns=%d channel=%s",
            request_id,
            profile_id,
            len(question),
            len(bounded),
            safe_channel,
        )
        try:
            result = get_graph().invoke(
                {
                    "profile_id": str(profile_id),
                    "question": question,
                    "conversation_history": history_dicts,
                    "channel": safe_channel,
                    "request_id": request_id,
                },
                config={
                    "configurable": {
                        "db": db,
                        "sentence_queue": sentence_queue,
                        "cancel_event": cancel_event,
                    }
                },
            )
        except Exception as exc:
            error_type = type(exc).__name__
            logger.error(
                "agent_request_failed request_id=%s profile_id=%s error_type=%s "
                "success=false total_latency_ms=%d",
                request_id,
                profile_id,
                error_type,
                int((time.perf_counter() - started) * 1000),
            )
            raise

        sources = []
        for item in result.get("source_references") or []:
            sources.append(
                SourceReference(
                    document_id=uuid.UUID(str(item["document_id"])),
                    filename=item["filename"],
                    page_number=item["page_number"],
                    chunk_index=item["chunk_index"],
                    score=item.get("score"),
                    excerpt=item.get("excerpt"),
                )
            )

        status_raw = result.get("evidence_status") or EvidenceStatus.NO_EVIDENCE.value
        try:
            evidence_status = EvidenceStatus(status_raw)
        except ValueError:
            evidence_status = EvidenceStatus.NO_EVIDENCE

        logger.info(
            "agent_request_finished request_id=%s profile_id=%s channel=%s "
            "intent=%s rewrite_applied=%s retrieval_query_len=%d "
            "retrieved_chunk_count=%d evidence_status=%s success=true "
            "error_type=none total_latency_ms=%d",
            request_id,
            profile_id,
            safe_channel,
            result.get("intent") or "none",
            bool(result.get("query_rewritten")),
            len(result.get("retrieval_query") or question),
            len(result.get("retrieved_chunks") or result.get("source_references") or []),
            evidence_status.value,
            int((time.perf_counter() - started) * 1000),
        )

        answer = result.get("answer") or ""
        return AskResponse(
            question=question,
            answer=answer,
            sources=sources,
            evidence_status=evidence_status,
            intent=result.get("intent"),
            contact_status=result.get("contact_status"),
            summary=_turn_summary(
                profile, question, answer, result.get("intent"), evidence_status.value
            ),
        )
