"""Layer 6 voice routes: status + live WebSocket. Profile id comes from the path."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, WebSocket

from app.schemas.voice import VoiceReadyResponse
from app.services import voice_runtime, voice_service

router = APIRouter(prefix="/voice", tags=["voice"])


@router.get("/ready", response_model=VoiceReadyResponse)
def voice_ready() -> VoiceReadyResponse:
    return VoiceReadyResponse(voice_ready=voice_service.voice_ready())


@router.websocket("/profiles/{profile_id}/live")
async def private_voice_live(websocket: WebSocket, profile_id: uuid.UUID) -> None:
    await voice_runtime.run_live_session(websocket, profile_id, public=False)
