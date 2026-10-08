"""
public_service.py — Layer 4 / 4.1 public profile and public RAG.

This is the security boundary between private management APIs and the
shareable professional representative.

Responsibilities:
  - Confirm the profile exists AND is_public
  - Return a PublicProfile with only professional-representation fields
  - Delegate questions to the LangGraph agent (which reuses rag_service)
  - Strip internal identifiers from source references

Does NOT:
  - Mutate profiles, documents, or Qdrant
  - Expose contact_preferences, timestamps, storage paths, indexing errors
  - Distinguish "not found" from "not public" in the HTTP response
"""

import os
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Document, Profile
from app.schemas.knowledge import IndexingStatus
from app.schemas.public import PublicAskResponse, PublicProfile, PublicSourceReference
from app.schemas.rag import AskResponse, ConversationTurn
from app.services import agent_service

_NOT_FOUND_DETAIL = "Profile not found."


def _require_public_profile(db: Session, profile_id: uuid.UUID) -> Profile:
    """
    Return the profile only if it exists and is_public is True.

    Missing and private profiles both raise 404 with the same message so
    callers cannot enumerate private profiles.
    """
    profile = db.get(Profile, profile_id)
    if profile is None or not profile.is_public:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_NOT_FOUND_DETAIL,
        )
    return profile


def _knowledge_ready(db: Session, profile_id: uuid.UUID) -> bool:
    """True when at least one document is INDEXED. Does not leak counts."""
    count = (
        db.query(Document)
        .filter(
            Document.profile_id == profile_id,
            Document.indexing_status == IndexingStatus.INDEXED.value,
        )
        .count()
    )
    return count > 0


def _sanitize_filename(filename: str) -> str:
    """Return only the basename so a leaked path cannot reach the client."""
    name = os.path.basename((filename or "").replace("\\", "/"))
    return name or "document.pdf"


def _to_public_sources(private: AskResponse) -> list[PublicSourceReference]:
    return [
        PublicSourceReference(
            filename=_sanitize_filename(src.filename),
            page_number=src.page_number,
        )
        for src in private.sources
    ]


def get_public_profile(db: Session, profile_id: uuid.UUID) -> PublicProfile:
    """Load a public professional profile, or 404 if it is not shareable."""
    profile = _require_public_profile(db, profile_id)
    return PublicProfile(
        id=str(profile.id),
        name=profile.name,
        headline=profile.headline,
        about=profile.about,
        skills=profile.skills,
        experience=profile.experience,
        projects=profile.projects,
        education=profile.education,
        knowledge_ready=_knowledge_ready(db, profile.id),
    )


def ask_public_profile(
    db: Session,
    profile_id: uuid.UUID,
    question: str,
    conversation_history: list[ConversationTurn] | None = None,
    channel: str = "text",
    sentence_queue=None,
    cancel_event=None,
) -> PublicAskResponse:
    """
    Answer a public visitor's question using the existing RAG pipeline.

    profile_id is taken from the URL path. Conversation history cannot
    change which profile is queried.
    """
    _require_public_profile(db, profile_id)

    private_response = agent_service.handle_question(
        db=db,
        profile_id=profile_id,
        question=question,
        conversation_history=conversation_history,
        channel=channel,
        sentence_queue=sentence_queue,
        cancel_event=cancel_event,
    )

    return PublicAskResponse(
        question=private_response.question,
        answer=private_response.answer,
        sources=_to_public_sources(private_response),
        evidence_status=private_response.evidence_status,
        intent=private_response.intent,
        contact_status=private_response.contact_status,
        # Names only from public profile fields + the visible Q/A; no document text.
        summary=private_response.summary,
    )
