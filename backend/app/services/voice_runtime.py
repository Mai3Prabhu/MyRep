"""Realtime WebSocket session: browser ↔ FastAPI ↔ Sarvam STT/TTS ↔ LangGraph.

Turn lifecycle for one live session:

    LISTENING --accepted final--> THINKING --first TTS audio--> SPEAKING
        ^                             |                            |
        |                             +------- turn finished ------+
        |                                          |
        |                    no audio sent         |  audio sent
        +------------------------------------------+-----> AWAITING_PLAYBACK
        |                                                       |
        +------ playback_done(turn_id) / interrupt(turn_id) ----+

Guarantees:
  - Microphone audio is forwarded to STT only while LISTENING, so the Rep's
    own speech cannot be transcribed into a user turn.
  - A final transcript starts a turn only while LISTENING and only if new
    browser audio arrived after LISTENING began. Duplicate and stale finals
    are dropped and logged with a reason.
  - One accepted final runs the agent exactly once.
  - Every turn-scoped message carries turn_id. A superseded or interrupted
    turn sends nothing further, and its late output is discarded.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import re
import time
import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

from app.core import voice_timing
from app.db.database import SessionLocal
from app.schemas.rag import ConversationTurn
from app.services import sarvam_service, voice_service
from app.services.sarvam_service import SarvamError, SarvamNotConfigured

logger = logging.getLogger(__name__)

_SAFE_UNAVAILABLE = "This profile is not available."
_SAFE_VOICE_DOWN = "Voice is temporarily unavailable. You can continue in text chat."
_TURN_FAILED = "I couldn't answer that right now. Please try again."

LISTENING = "listening"
THINKING = "thinking"
SPEAKING = "speaking"
AWAITING_PLAYBACK = "awaiting_playback"

# PCM from Bulbul: 16-bit mono at 24 kHz.
_PCM_BYTES_PER_SECOND = 24000 * 2
# Liveness only: if the browser never reports playback_done (tab closed,
# old client), return to LISTENING after the audio we sent has had time to play.
_PLAYBACK_GRACE_SECONDS = 1.5

_WORD_RE = re.compile(r"[a-z0-9']+")


@dataclass
class _Turn:
    turn_id: int
    question: str
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    spoken: list[str] = field(default_factory=list)
    audio_bytes: int = 0
    first_audio_at: float = 0.0
    history_recorded: bool = False


def _words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def is_echo_of_answer(transcript: str, answer: str) -> bool:
    """
    Secondary safeguard: the transcript is the Rep's own previous answer.

    Compares against the last ANSWER, never the last question, so a visitor
    can always ask the same question again.
    """
    heard = _words(transcript)
    said = _words(answer)
    if len(heard) < 3 or not said:
        return False
    said_text = " ".join(said)
    if " ".join(heard) in said_text:
        return True
    said_set = set(said)
    overlap = sum(1 for word in heard if word in said_set) / len(heard)
    return overlap >= 0.85


def _error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException) and exc.status_code == 429:
        return "The language model quota is exhausted. Please try again later."
    if isinstance(exc, HTTPException) and exc.status_code == 401:
        return "The language model key was rejected. Update the API key and try again."
    return _TURN_FAILED


class _LiveSession:
    def __init__(self, websocket: WebSocket, stt, profile_id: uuid.UUID, public: bool):
        self.ws = websocket
        self.stt = stt
        self.profile_id = profile_id
        self.public = public
        self.phase = LISTENING
        self.turn: _Turn | None = None
        self.turn_seq = 0
        self.history: list[ConversationTurn] = []
        self.last_answer = ""
        self.frames_since_listening = 0
        self.frames_total = 0
        self.frames_dropped = 0
        self.last_frame_at = 0.0
        self.turn_task: asyncio.Task | None = None
        self.fallback_task: asyncio.Task | None = None
        self.closed = asyncio.Event()

    # ── state ────────────────────────────────────────────────────────────

    def is_current(self, turn: _Turn) -> bool:
        return self.turn is turn and not turn.cancel.is_set()

    def _set_phase(self, phase: str) -> None:
        if phase != self.phase:
            logger.info(
                "voice_phase turn_id=%d from=%s to=%s",
                self.turn.turn_id if self.turn else 0,
                self.phase,
                phase,
            )
        self.phase = phase

    async def enter_listening(self, reason: str) -> None:
        if self.fallback_task is not None:
            self.fallback_task.cancel()
            self.fallback_task = None
        self._set_phase(LISTENING)
        self.frames_since_listening = 0
        logger.info(
            "voice_listening turn_id=%d reason=%s",
            self.turn.turn_id if self.turn else 0,
            reason,
        )
        await _send(
            self.ws,
            {
                "type": "status",
                "state": "listening",
                "turn_id": self.turn.turn_id if self.turn else 0,
            },
        )

    def final_drop_reason(self, text: str) -> str | None:
        if not text:
            return "empty"
        if self.phase != LISTENING:
            return f"phase_{self.phase}"
        if self.frames_since_listening == 0:
            # Nothing was heard since the last turn ended, so this final
            # belongs to audio that was already answered.
            return "no_new_audio"
        if self.last_answer and is_echo_of_answer(text, self.last_answer):
            return "echo_of_answer"
        return None

    def record_history(self, turn: _Turn, answer: str) -> None:
        """Append one turn to history at most once."""
        if turn.history_recorded:
            return
        turn.history_recorded = True
        self.history = voice_service.append_history(self.history, turn.question, answer)
        if answer:
            self.last_answer = answer

    # ── browser → server ─────────────────────────────────────────────────

    async def on_audio(self, data: str) -> None:
        now = time.perf_counter()
        self.frames_total += 1
        if self.phase != LISTENING:
            # The browser mutes the mic while the Rep speaks; this also
            # protects against older clients and residual echo.
            self.frames_dropped += 1
            return
        self.frames_since_listening += 1
        if self.frames_total == 1 or (
            self.last_frame_at and (now - self.last_frame_at) > 0.5
        ):
            logger.info(
                "stt_audio_frame n=%d b64_chars=%d gap_ms=%d dropped=%d",
                self.frames_total,
                len(data),
                0 if self.frames_total == 1 else int((now - self.last_frame_at) * 1000),
                self.frames_dropped,
            )
        self.last_frame_at = now
        await self.stt.send_audio_b64(data)

    async def on_interrupt(self, turn_id) -> None:
        turn = self.turn
        if turn is None or self.phase == LISTENING or (
            turn_id is not None and turn_id != turn.turn_id
        ):
            logger.info(
                "voice_interrupt_ignored turn_id=%s current=%d phase=%s",
                turn_id,
                turn.turn_id if turn else 0,
                self.phase,
            )
            return
        logger.info("voice_turn_interrupted turn_id=%d phase=%s", turn.turn_id, self.phase)
        if turn.spoken:
            # The visitor heard part of the answer; keep it as context.
            self.record_history(turn, " ".join(turn.spoken))
        else:
            turn.history_recorded = True
        turn.cancel.set()
        await self.enter_listening("interrupt")

    async def on_playback_done(self, turn_id) -> None:
        turn = self.turn
        if (
            turn is None
            or self.phase != AWAITING_PLAYBACK
            or (turn_id is not None and turn_id != turn.turn_id)
        ):
            logger.info(
                "voice_playback_done_ignored turn_id=%s current=%d phase=%s",
                turn_id,
                turn.turn_id if turn else 0,
                self.phase,
            )
            return
        await self.enter_listening("playback_done")

    async def from_browser(self) -> None:
        try:
            while True:
                message = await self.ws.receive_json()
                kind = message.get("type")
                if kind == "audio":
                    data = message.get("data")
                    if isinstance(data, str) and data:
                        await self.on_audio(data)
                elif kind == "interrupt":
                    await self.on_interrupt(message.get("turn_id"))
                elif kind == "playback_done":
                    await self.on_playback_done(message.get("turn_id"))
                elif kind == "end":
                    await self.stt.send_end()
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.error("voice_browser_recv_failed profile_id=%s", self.profile_id)
        finally:
            self.closed.set()

    # ── STT → server ─────────────────────────────────────────────────────

    async def from_stt(self) -> None:
        try:
            async for event in self.stt.events():
                if self.closed.is_set():
                    break
                ev = event.get("event")
                if ev == "transcript.partial":
                    text = (event.get("text") or "").strip()
                    if text and self.phase == LISTENING:
                        await _send(self.ws, {"type": "partial", "text": text})
                elif ev == "vad.speech_start":
                    if self.phase == LISTENING:
                        await _send(
                            self.ws,
                            {
                                "type": "status",
                                "state": "listening",
                                "turn_id": self.turn.turn_id if self.turn else 0,
                            },
                        )
                elif ev == "transcript.final":
                    text = (event.get("text") or "").strip()
                    reason = self.final_drop_reason(text)
                    if reason is not None:
                        logger.info(
                            "voice_final_dropped reason=%s phase=%s current_turn=%d text_len=%d",
                            reason,
                            self.phase,
                            self.turn.turn_id if self.turn else 0,
                            len(text),
                        )
                        continue
                    self.start_turn(text)
                elif ev == "error":
                    logger.error("sarvam_stt_event_error")
                    if event.get("is_fatal"):
                        await _send(self.ws, {"type": "error", "message": _SAFE_VOICE_DOWN})
                        break
            # The STT stream ended. Let an in-flight turn finish its answer.
            if self.turn_task is not None and not self.turn_task.done():
                await asyncio.gather(self.turn_task, return_exceptions=True)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.error("voice_stt_loop_failed error=%s", type(exc).__name__)
            await _send(self.ws, {"type": "error", "message": _SAFE_VOICE_DOWN})
        finally:
            self.closed.set()

    # ── one turn ─────────────────────────────────────────────────────────

    def start_turn(self, text: str) -> None:
        self.turn_seq += 1
        turn = _Turn(turn_id=self.turn_seq, question=text)
        self.turn = turn
        # Set synchronously so the next STT event already sees THINKING.
        self._set_phase(THINKING)
        logger.info("voice_turn_started turn_id=%d question_len=%d", turn.turn_id, len(text))
        self.turn_task = asyncio.create_task(self.run_turn(turn))

    def _run_agent(self, turn: _Turn, sentence_q: queue.Queue, history: list) -> dict:
        turn_db = SessionLocal()
        try:
            return voice_service.answer_turn(
                turn_db,
                self.profile_id,
                turn.question,
                history,
                public=self.public,
                sentence_queue=sentence_q,
                cancel_event=turn.cancel,
            )
        finally:
            turn_db.close()

    async def run_turn(self, turn: _Turn) -> None:
        await _send(self.ws, {"type": "final", "text": turn.question, "turn_id": turn.turn_id})
        await _send(self.ws, {"type": "status", "state": "thinking", "turn_id": turn.turn_id})
        agent_started = time.perf_counter()
        voice_timing.begin()
        sentence_q: queue.Queue = queue.Queue()
        tts_ready = asyncio.create_task(sarvam_service.open_pcm_tts(turn.cancel))
        consumer = asyncio.create_task(self._consume_sentences(turn, sentence_q, tts_ready))

        result: dict | None = None
        error: Exception | None = None
        try:
            result = await asyncio.to_thread(
                self._run_agent, turn, sentence_q, list(self.history)
            )
        except Exception as exc:
            error = exc
            logger.error(
                "voice_turn_failed turn_id=%d profile_id=%s error=%s",
                turn.turn_id,
                self.profile_id,
                type(exc).__name__,
            )
        finally:
            sentence_q.put(None)
        await consumer

        if not self.is_current(turn):
            logger.info("voice_turn_superseded turn_id=%d", turn.turn_id)
            return

        logger.info(
            "agent_finished turn_id=%d latency_ms=%d answer_len=%d",
            turn.turn_id,
            int((time.perf_counter() - agent_started) * 1000),
            len((result or {}).get("answer") or ""),
        )
        await _emit_timings(self.ws, turn.turn_id)

        if error is not None:
            answer = _error_message(error)
            await _send(self.ws, {"type": "error", "message": answer, "turn_id": turn.turn_id})
            await _send(self.ws, {"type": "answer", "text": answer, "turn_id": turn.turn_id})
        else:
            answer = result.get("answer") or ""
            await _send(
                self.ws,
                {
                    "type": "answer",
                    "text": answer,
                    "turn_id": turn.turn_id,
                    "final": True,
                    "intent": result.get("intent"),
                    "contact_status": result.get("contact_status"),
                    "evidence_status": result.get("evidence_status"),
                    "sources": result.get("sources") or [],
                    "summary": result.get("summary"),
                },
            )

        if not turn.spoken and answer and self.is_current(turn):
            # The full text is already on screen; keep it if speech is interrupted.
            turn.spoken.append(answer)
            self._set_phase(SPEAKING)
            await _send(self.ws, {"type": "status", "state": "speaking", "turn_id": turn.turn_id})
            await _speak(self, turn, answer)

        if not self.is_current(turn):
            return
        if error is None:
            self.record_history(turn, answer)
        else:
            # A failed turn is not conversation context.
            turn.history_recorded = True
        await self.finish_turn(turn)

    async def finish_turn(self, turn: _Turn) -> None:
        awaiting = turn.audio_bytes > 0
        await _send(
            self.ws,
            {"type": "turn_complete", "turn_id": turn.turn_id, "awaiting_playback": awaiting},
        )
        if not awaiting:
            await self.enter_listening("no_audio")
            return
        self._set_phase(AWAITING_PLAYBACK)
        played = time.perf_counter() - turn.first_audio_at if turn.first_audio_at else 0.0
        remaining = max(0.0, turn.audio_bytes / _PCM_BYTES_PER_SECOND - played)
        self.fallback_task = asyncio.create_task(
            self._playback_fallback(turn, remaining + _PLAYBACK_GRACE_SECONDS)
        )

    async def _playback_fallback(self, turn: _Turn, delay: float) -> None:
        await asyncio.sleep(delay)
        if self.turn is turn and self.phase == AWAITING_PLAYBACK:
            self.fallback_task = None
            logger.info("voice_playback_done_fallback turn_id=%d", turn.turn_id)
            await self.enter_listening("playback_fallback")

    async def _consume_sentences(
        self, turn: _Turn, sentence_q: queue.Queue, tts_ready: asyncio.Task
    ) -> None:
        """Speak streamed sentences in order. Never raises."""
        session = None
        forward = None
        try:
            while True:
                item = await asyncio.to_thread(sentence_q.get)
                if item is None:
                    break
                if not self.is_current(turn):
                    continue
                if session is None:
                    voice_timing.mark("tts_request_start")
                    voice_timing.mark("first_sentence_tts_start")
                    await _emit_timings(self.ws, turn.turn_id)
                    self._set_phase(SPEAKING)
                    await _send(
                        self.ws, {"type": "status", "state": "speaking", "turn_id": turn.turn_id}
                    )
                    session = await tts_ready
                    forward = asyncio.create_task(_forward_pcm(self, turn, session))
                turn.spoken.append(item)
                await _send(
                    self.ws,
                    {"type": "answer", "text": " ".join(turn.spoken), "turn_id": turn.turn_id},
                )
                await session.send_sentence(item)
                await _emit_timings(self.ws, turn.turn_id)
        except Exception as exc:
            logger.error("voice_tts_stream_failed turn_id=%d error=%s", turn.turn_id, type(exc).__name__)
            if isinstance(exc, SarvamError) and self.is_current(turn):
                await _send(
                    self.ws,
                    {
                        "type": "error",
                        "message": sarvam_service.public_error_message(exc),
                        "turn_id": turn.turn_id,
                    },
                )
            # The queue is unbounded, so the agent thread never blocks on put().
        finally:
            if session is not None:
                await session.finish()
                if forward is not None:
                    await asyncio.gather(forward, return_exceptions=True)
            else:
                await _release_unused_tts(tts_ready)

    # ── whole session ────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        self.closed.set()
        if self.turn is not None:
            self.turn.cancel.set()
        for task in (self.fallback_task, self.turn_task):
            if task is not None and not task.done():
                task.cancel()
        pending = [t for t in (self.fallback_task, self.turn_task) if t is not None]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


async def run_live_session(websocket: WebSocket, profile_id: uuid.UUID, *, public: bool) -> None:
    await websocket.accept()

    db = SessionLocal()
    try:
        name = voice_service.authorize_session(db, profile_id, public=public)
    except HTTPException:
        await _send(websocket, {"type": "error", "message": _SAFE_UNAVAILABLE})
        await websocket.close()
        return
    except Exception:
        logger.error("voice_authorize_failed profile_id=%s", profile_id)
        await _send(websocket, {"type": "error", "message": _SAFE_UNAVAILABLE})
        await websocket.close()
        return
    finally:
        db.close()

    if not voice_service.voice_ready():
        await _send(
            websocket,
            {
                "type": "error",
                "message": "Voice is not configured on the server yet. Use text chat instead.",
            },
        )
        await websocket.close()
        return

    await _send(
        websocket,
        {
            "type": "ready",
            "profile_name": name,
            "sample_rate": 16000,
            "encoding": "linear16",
        },
    )

    try:
        stt = await sarvam_service.open_stt()
    except (SarvamNotConfigured, SarvamError) as exc:
        await _send(
            websocket,
            {"type": "error", "message": sarvam_service.public_error_message(exc)},
        )
        await websocket.close()
        return

    session = _LiveSession(websocket, stt, profile_id, public)
    tasks: list[asyncio.Task] = []
    try:
        await _send(websocket, {"type": "status", "state": "listening", "turn_id": 0})
        tasks = [
            asyncio.create_task(session.from_browser()),
            asyncio.create_task(session.from_stt()),
        ]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        await session.shutdown()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await stt.close()
        try:
            await websocket.close()
        except Exception:
            pass


async def _release_unused_tts(tts_ready: asyncio.Task) -> None:
    """Close a TTS socket that was opened (or is opening) but never used.

    asyncio.wait never raises, so cancelling a half-open connect cannot leak
    CancelledError into the turn and tear down the whole session.
    """
    if not tts_ready.done():
        tts_ready.cancel()
    await asyncio.wait({tts_ready})
    if tts_ready.cancelled() or tts_ready.exception() is not None:
        return
    try:
        await tts_ready.result().close()
    except Exception:
        pass


async def _audio_out(session: _LiveSession, turn: _Turn, chunk: dict) -> None:
    if turn.first_audio_at == 0.0:
        turn.first_audio_at = time.perf_counter()
    audio = chunk["audio"]
    turn.audio_bytes += (len(audio) * 3) // 4
    await _send(
        session.ws,
        {
            "type": "audio",
            "content_type": chunk.get("content_type") or "audio/pcm",
            "sample_rate": chunk.get("sample_rate") or 24000,
            "turn_id": turn.turn_id,
            "data": audio,
        },
    )


async def _forward_pcm(session: _LiveSession, turn: _Turn, tts) -> None:
    chunks = 0
    try:
        async for chunk in tts.chunks():
            if not session.is_current(turn):
                logger.info("tts_cancelled turn_id=%d chunks=%d", turn.turn_id, chunks)
                break
            chunks += 1
            if chunks == 1:
                voice_timing.mark("tts_first_chunk_received")
                voice_timing.mark("first_sentence_tts_first_pcm")
                await _emit_timings(session.ws, turn.turn_id)
            await _audio_out(session, turn, chunk)
        voice_timing.mark("tts_last_chunk_received")
        await _emit_timings(session.ws, turn.turn_id)
    except SarvamError as exc:
        if session.is_current(turn):
            await _send(
                session.ws,
                {
                    "type": "error",
                    "message": sarvam_service.public_error_message(exc),
                    "turn_id": turn.turn_id,
                },
            )
    finally:
        if session.is_current(turn):
            await _send(session.ws, {"type": "audio_end", "turn_id": turn.turn_id})


async def _speak(session: _LiveSession, turn: _Turn, text: str) -> None:
    started = time.perf_counter()
    chunks = 0
    voice_timing.mark("tts_request_start")
    await _emit_timings(session.ws, turn.turn_id)
    try:
        async for chunk in sarvam_service.stream_tts(text, turn.cancel):
            if not session.is_current(turn):
                logger.info("tts_cancelled turn_id=%d chunks=%d", turn.turn_id, chunks)
                break
            chunks += 1
            if chunks == 1:
                voice_timing.mark("tts_first_chunk_received")
                await _emit_timings(session.ws, turn.turn_id)
                logger.info(
                    "tts_first_audio_sent turn_id=%d latency_ms=%d",
                    turn.turn_id,
                    int((time.perf_counter() - started) * 1000),
                )
            await _audio_out(session, turn, chunk)
        voice_timing.mark("tts_last_chunk_received")
        await _emit_timings(session.ws, turn.turn_id)
    except SarvamError as exc:
        if session.is_current(turn):
            await _send(
                session.ws,
                {
                    "type": "error",
                    "message": sarvam_service.public_error_message(exc),
                    "turn_id": turn.turn_id,
                },
            )
    finally:
        if session.is_current(turn):
            await _send(session.ws, {"type": "audio_end", "turn_id": turn.turn_id})


async def _emit_timings(websocket: WebSocket, turn_id: int) -> None:
    marks = voice_timing.snapshot()
    if not marks:
        return
    await _send(websocket, {"type": "timing", "turn_id": turn_id, "marks": marks})


async def _send(websocket: WebSocket, payload: dict) -> None:
    try:
        await websocket.send_json(payload)
    except Exception:
        pass
