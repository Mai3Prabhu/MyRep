"""
voice_service.py — Layer 6 MyRep voice application logic.

Sarvam handles STT/TTS. This module:
  - validates public/private access
  - invokes agent_service.handle_question (existing LangGraph)
  - keeps bounded conversation history for the live session

It does not talk to Qdrant or Gemini directly.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core import voice_timing
from app.schemas.rag import ConversationTurn
from app.services import agent_service, public_service, rag_service, sarvam_service

logger = logging.getLogger(__name__)


def voice_ready() -> bool:
    return sarvam_service.configured()


def authorize_session(db: Session, profile_id: uuid.UUID, *, public: bool) -> str:
    """Return the profile name after enforcing public/private rules."""
    if public:
        profile = public_service.get_public_profile(db, profile_id)
        return profile.name
    from app.services import profile_service

    row = profile_service.get_profile(db, profile_id)
    return row.name


def answer_turn(
    db: Session,
    profile_id: uuid.UUID,
    question: str,
    conversation_history: list[ConversationTurn],
    *,
    public: bool,
    claimed_profile_id: str | None = None,
    sentence_queue=None,
    cancel_event=None,
) -> dict:
    """
    One finalized voice utterance → existing graph.

    claimed_profile_id from any client/model payload is ignored.
    """
    if claimed_profile_id:
        logger.info(
            "voice_ignored_claimed_profile token_profile_id=%s claimed=%s",
            profile_id,
            str(claimed_profile_id)[:64],
        )

    question = (question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    bounded = rag_service.bound_conversation_history(conversation_history)

    logger.info(
        "voice_request_started profile_id=%s public=%s question_len=%d history_turns=%d",
        profile_id,
        public,
        len(question),
        len(bounded),
    )
    voice_timing.ensure()
    voice_timing.mark("transcript_processing_start")

    if public:
        result = public_service.ask_public_profile(
            db=db,
            profile_id=profile_id,
            question=question,
            conversation_history=bounded,
            channel="voice",
            sentence_queue=sentence_queue,
            cancel_event=cancel_event,
        )
        sources = [s.model_dump() for s in result.sources]
        return {
            "answer": result.answer,
            "intent": result.intent,
            "contact_status": result.contact_status,
            "evidence_status": result.evidence_status.value,
            "sources": sources,
            "summary": result.summary.model_dump() if result.summary else None,
            "timings": voice_timing.snapshot(),
        }

    result = agent_service.handle_question(
        db=db,
        profile_id=profile_id,
        question=question,
        conversation_history=bounded,
        channel="voice",
        sentence_queue=sentence_queue,
        cancel_event=cancel_event,
    )
    return {
        "answer": result.answer,
        "intent": result.intent,
        "contact_status": result.contact_status,
        "evidence_status": result.evidence_status.value,
        "sources": [
            {"filename": s.filename, "page_number": s.page_number, "excerpt": s.excerpt}
            for s in result.sources
        ],
        "summary": result.summary.model_dump() if result.summary else None,
        "timings": voice_timing.snapshot(),
    }


def append_history(
    history: list[ConversationTurn],
    question: str,
    answer: str,
) -> list[ConversationTurn]:
    history.append(ConversationTurn(role="user", content=question[:4000]))
    if answer:
        history.append(ConversationTurn(role="assistant", content=answer[:4000]))
    return rag_service.bound_conversation_history(history)
