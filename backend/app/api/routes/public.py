"""
Public endpoints for Layers 4 / 4.1 / 6.

These routes are intentionally separate from /api/v1/profiles and
/api/v1/documents. Public visitors can only read a shareable professional
profile, ask grounded questions, and start a public voice session.
"""

import uuid

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.public import PublicAskResponse, PublicProfile
from app.schemas.rag import AskRequest
from app.services import public_service, voice_runtime

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/profiles/{profile_id}", response_model=PublicProfile)
def get_public_profile(
    profile_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> PublicProfile:
    """
    Return the professional representation of a public profile.

    Returns 404 for missing profiles and for profiles that are not public,
    with the same error message in both cases.
    """
    return public_service.get_public_profile(db, profile_id)


@router.post("/profiles/{profile_id}/ask", response_model=PublicAskResponse)
def ask_public_profile(
    profile_id: uuid.UUID,
    payload: AskRequest,
    db: Session = Depends(get_db),
) -> PublicAskResponse:
    """
    Answer a question about a public profile using the existing RAG pipeline.

    profile_id comes from the URL path and is validated as public before
    retrieval. Conversation history is optional session context only.
    """
    return public_service.ask_public_profile(
        db=db,
        profile_id=profile_id,
        question=payload.question,
        conversation_history=payload.conversation_history or None,
    )


@router.websocket("/profiles/{profile_id}/voice/live")
async def public_voice_live(websocket: WebSocket, profile_id: uuid.UUID) -> None:
    """Public voice. Missing and private profiles get the same error."""
    await voice_runtime.run_live_session(websocket, profile_id, public=True)
