"""
sarvam_service.py — Sarvam STT/TTS adapter (Layer 6).

Owns WebSocket protocol for:
  - Saaras realtime STT  (wss://api.sarvam.ai/speech-to-text-realtime/ws)
  - Bulbul v3 streaming TTS (wss://api.sarvam.ai/text-to-speech/ws)

Does NOT call LangGraph, Qdrant, or Gemini.
The API key never leaves this module except as a request header.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from collections.abc import AsyncIterator
from urllib.parse import urlencode

import websockets

from app.core.config import settings

logger = logging.getLogger(__name__)

_STT_URL = "wss://api.sarvam.ai/speech-to-text-realtime/ws"
_TTS_URL = "wss://api.sarvam.ai/text-to-speech/ws"


class SarvamNotConfigured(RuntimeError):
    pass


class SarvamError(RuntimeError):
    pass


def configured() -> bool:
    return bool((settings.SARVAM_API_KEY or "").strip())


def _headers() -> dict[str, str]:
    key = (settings.SARVAM_API_KEY or "").strip()
    if not key:
        raise SarvamNotConfigured("sarvam_not_configured")
    return {"Api-Subscription-Key": key}


def _connect_kwargs(headers: dict[str, str]) -> dict:
    params = inspect.signature(websockets.connect).parameters
    if "additional_headers" in params:
        return {"additional_headers": headers}
    return {"extra_headers": headers}


def public_error_message(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    key = (settings.SARVAM_API_KEY or "").strip()
    if key and key in text:
        text = text.replace(key, "[redacted]")
    lowered = text.lower()
    if "subscription" in lowered or "401" in text or "1003" in text:
        return "Voice service is temporarily unavailable."
    return "Voice service is temporarily unavailable."


def _stt_url() -> str:
    model = (settings.SARVAM_STT_MODEL or "saaras:v3-realtime").strip()
    query = urlencode(
        {
            "language_code": "en-IN",
            "model": model,
            "stream_type": "fast",
            "mode": "transcribe",
            "endpointing": "vad",
            "encoding": "linear16",
            "sample_rate": "16000",
        }
    )
    return f"{_STT_URL}?{query}"


def _tts_url() -> str:
    model = (settings.SARVAM_TTS_MODEL or "bulbul:v3").strip()
    query = urlencode({"model": model, "send_completion_event": "true"})
    return f"{_TTS_URL}?{query}"


class SttSession:
    def __init__(self, ws):
        self._ws = ws

    async def send_audio_b64(self, audio_b64: str) -> None:
        await self._ws.send(json.dumps({"event": "audio_input", "audio": audio_b64}))

    async def send_end(self) -> None:
        await self._ws.send(json.dumps({"event": "end"}))

    async def events(self) -> AsyncIterator[dict]:
        async for raw in self._ws:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            yield message

    async def close(self) -> None:
        try:
            await self._ws.close()
        except Exception:
            pass


async def open_stt() -> SttSession:
    headers = _headers()
    try:
        ws = await websockets.connect(
            _stt_url(),
            **_connect_kwargs(headers),
            ping_interval=20,
            ping_timeout=20,
            max_size=2**23,
        )
    except Exception as exc:
        logger.error("sarvam_stt_connect_failed error=%s", type(exc).__name__)
        raise SarvamError("stt_unavailable") from exc
    return SttSession(ws)


async def stream_tts(
    text: str,
    cancel: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, str]]:
    """
    Yield {content_type, audio} dicts of base64 audio until complete or cancelled.
    """
    spoken = (text or "").strip()[:2500]
    if not spoken:
        return
    headers = _headers()
    try:
        ws = await websockets.connect(
            _tts_url(),
            **_connect_kwargs(headers),
            ping_interval=20,
            ping_timeout=20,
            max_size=2**23,
        )
    except Exception as exc:
        logger.error("sarvam_tts_connect_failed error=%s", type(exc).__name__)
        raise SarvamError("tts_unavailable") from exc

    try:
        await ws.send(
            json.dumps(
                {
                    "type": "config",
                    "data": {
                        "model": (settings.SARVAM_TTS_MODEL or "bulbul:v3").strip(),
                        "language_code": (settings.SARVAM_TTS_LANGUAGE or "en-IN").strip(),
                        "speaker": (settings.SARVAM_TTS_SPEAKER or "shubh").strip(),
                        "speech_sample_rate": "24000",
                        # linear16 is raw PCM. MP3 chunks are one bitstream split
                        # mid-frame, so the browser cannot decode them separately.
                        "output_audio_codec": "linear16",
                    },
                }
            )
        )
        await ws.send(json.dumps({"type": "text", "data": {"text": spoken}}))
        await ws.send(json.dumps({"type": "flush"}))
        started = time.perf_counter()
        n_audio = 0
        logger.info("tts_started chars=%d", len(spoken))

        async for raw in ws:
            if cancel is not None and cancel.is_set():
                break
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            kind = message.get("type")
            if kind == "audio":
                data = message.get("data") or {}
                audio = data.get("audio")
                if isinstance(audio, str) and audio:
                    content_type = data.get("content_type") or "audio/pcm"
                    if n_audio == 0:
                        logger.info(
                            "tts_first_audio content_type=%s bytes=%d latency_ms=%d",
                            content_type,
                            len(audio),
                            int((time.perf_counter() - started) * 1000),
                        )
                    n_audio += 1
                    yield {
                        "content_type": content_type,
                        "audio": audio,
                        "sample_rate": 24000,
                    }
            elif kind == "event" and (message.get("data") or {}).get("event_type") == "final":
                break
            elif kind == "error":
                logger.error("sarvam_tts_error")
                raise SarvamError("tts_unavailable")
    finally:
        try:
            await ws.close()
        except Exception:
            pass


class PcmTtsSession:
    """One Bulbul socket. Sentences are flushed onto that socket in order."""

    def __init__(self, cancel: asyncio.Event | None = None):
        self._cancel = cancel
        self._ws = None
        self._audio: asyncio.Queue = asyncio.Queue()
        self._reader: asyncio.Task | None = None
        self._input_done = False
        self._flush_count = 0
        self._final_count = 0

    async def open(self) -> None:
        headers = _headers()
        try:
            self._ws = await websockets.connect(
                _tts_url(),
                **_connect_kwargs(headers),
                ping_interval=20,
                ping_timeout=20,
                max_size=2**23,
            )
        except Exception as exc:
            logger.error("sarvam_tts_connect_failed error=%s", type(exc).__name__)
            raise SarvamError("tts_unavailable") from exc
        await self._ws.send(
            json.dumps(
                {
                    "type": "config",
                    "data": {
                        "model": (settings.SARVAM_TTS_MODEL or "bulbul:v3").strip(),
                        "language_code": (settings.SARVAM_TTS_LANGUAGE or "en-IN").strip(),
                        "speaker": (settings.SARVAM_TTS_SPEAKER or "shubh").strip(),
                        "speech_sample_rate": "24000",
                        "output_audio_codec": "linear16",
                        "min_buffer_size": 30,
                    },
                }
            )
        )
        self._reader = asyncio.create_task(self._read())

    async def send_sentence(self, text: str) -> None:
        if self._cancel is not None and self._cancel.is_set():
            return
        if self._ws is None:
            return
        spoken = (text or "").strip()[:2500]
        if not spoken:
            return
        await self._ws.send(json.dumps({"type": "text", "data": {"text": spoken}}))
        await self._ws.send(json.dumps({"type": "flush"}))
        self._flush_count += 1

    def input_complete(self) -> None:
        self._input_done = True

    async def close(self) -> None:
        """Drop the socket when no speech was sent."""
        self._input_done = True
        reader = self._reader
        self._reader = None
        if reader is not None and not reader.done():
            reader.cancel()
            try:
                await reader
            except asyncio.CancelledError:
                pass
        elif reader is None:
            await self._audio.put(None)

    async def finish(self) -> None:
        self._input_done = True
        reader = self._reader
        if reader is None:
            await self._audio.put(None)
            return
        if reader.done():
            return
        try:
            await asyncio.wait_for(reader, timeout=25)
        except asyncio.TimeoutError:
            logger.info("tts_finish_timeout flushes=%d finals=%d", self._flush_count, self._final_count)
            if not reader.done():
                reader.cancel()

    async def chunks(self) -> AsyncIterator[dict[str, str]]:
        while True:
            item = await self._audio.get()
            if item is None:
                break
            yield item

    async def _read(self) -> None:
        try:
            while self._ws is not None:
                if self._cancel is not None and self._cancel.is_set():
                    break
                try:
                    raw = await asyncio.wait_for(self._ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    if (
                        self._input_done
                        and self._flush_count > 0
                        and self._final_count >= self._flush_count
                    ):
                        break
                    continue
                except Exception:
                    break
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                kind = message.get("type")
                if kind == "audio":
                    data = message.get("data") or {}
                    audio = data.get("audio")
                    if isinstance(audio, str) and audio:
                        await self._audio.put(
                            {
                                "content_type": data.get("content_type") or "audio/pcm",
                                "audio": audio,
                                "sample_rate": 24000,
                            }
                        )
                elif kind == "event" and (message.get("data") or {}).get("event_type") == "final":
                    self._final_count += 1
                elif kind == "error":
                    logger.error("sarvam_tts_error")
                    raise SarvamError("tts_unavailable")
        finally:
            await self._audio.put(None)
            if self._ws is not None:
                try:
                    await self._ws.close()
                except Exception:
                    pass


async def open_pcm_tts(cancel: asyncio.Event | None = None) -> PcmTtsSession:
    session = PcmTtsSession(cancel)
    await session.open()
    return session
