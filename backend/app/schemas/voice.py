"""Layer 6 voice status payload (WebSocket messages are untyped dicts)."""

from pydantic import BaseModel


class VoiceReadyResponse(BaseModel):
    voice_ready: bool
