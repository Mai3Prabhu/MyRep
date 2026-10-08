"""Layer 6 live-session tests. Sarvam WebSockets are faked.

The fakes model the real protocol:
  - FakeStt emits the next scripted transcript batch only when browser audio
    is forwarded to it (Sarvam transcribes audio it receives).
  - FakeBrowser speaks one utterance (one audio frame) each time the server
    says it is listening, reports playback_done after turn_complete, and ends
    the session once its utterances are used up.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import HTTPException, WebSocketDisconnect

from app.services import voice_runtime
from app.services.sarvam_service import SarvamError


PROFILE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
INSUFFICIENT = "I don't have enough information in the profile to answer that."


def final(text: str) -> dict:
    return {"event": "transcript.final", "text": text}


class FakeStt:
    def __init__(self, batches: list[list[dict]], *, end_after_last: bool = False):
        self.batches = [list(b) for b in batches]
        # Close the stream after the last batch, for scenarios where the last
        # utterance is (correctly) dropped and no turn would end the session.
        self.end_after_last = end_after_last
        self.audio: list[str] = []
        self.ended = False
        self.closed = False
        self._queue: asyncio.Queue | None = None

    @property
    def queue(self) -> asyncio.Queue:
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    def inject(self, event: dict) -> None:
        self.queue.put_nowait(event)

    async def send_audio_b64(self, audio_b64: str) -> None:
        self.audio.append(audio_b64)
        if self.batches:
            for event in self.batches.pop(0):
                self.queue.put_nowait(event)
            if not self.batches and self.end_after_last:
                self.queue.put_nowait(None)

    async def send_end(self) -> None:
        self.ended = True
        self.queue.put_nowait(None)

    async def events(self):
        while True:
            event = await self.queue.get()
            if event is None:
                return
            yield event

    async def close(self) -> None:
        self.closed = True
        self.queue.put_nowait(None)


class FakeBrowser:
    """The WebSocket as seen by the server."""

    def __init__(self, utterances: int, *, playback_done: bool = True):
        self.utterances = utterances
        self.auto_playback_done = playback_done
        self.sent: list[dict] = []
        self.closed = False
        self.on_send = None  # optional extra reaction, called after the default
        self._inbox: asyncio.Queue | None = None

    @property
    def inbox(self) -> asyncio.Queue:
        if self._inbox is None:
            self._inbox = asyncio.Queue()
        return self._inbox

    def push(self, message: dict) -> None:
        self.inbox.put_nowait(message)

    async def accept(self) -> None:
        return None

    async def receive_json(self) -> dict:
        message = await self.inbox.get()
        if message is None:
            raise WebSocketDisconnect()
        return message

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)
        kind = payload.get("type")
        if kind == "status" and payload.get("state") == "listening":
            if self.utterances > 0:
                self.utterances -= 1
                self.push({"type": "audio", "data": "AAAA"})
            else:
                self.push({"type": "end"})
        elif kind == "turn_complete" and payload.get("awaiting_playback"):
            if self.auto_playback_done:
                self.push({"type": "playback_done", "turn_id": payload["turn_id"]})
        if self.on_send is not None:
            self.on_send(payload, self)

    async def close(self) -> None:
        self.closed = True

    def of_type(self, kind: str, turn_id: int | None = None) -> list[dict]:
        return [
            m
            for m in self.sent
            if m.get("type") == kind and (turn_id is None or m.get("turn_id") == turn_id)
        ]


class DummySession:
    def close(self) -> None:
        return None


class FakePcm:
    """Streaming TTS socket: one audio chunk per sentence."""

    def __init__(self):
        self.sentences: list[str] = []
        self._queue: asyncio.Queue = asyncio.Queue()

    async def send_sentence(self, text: str) -> None:
        self.sentences.append(text)
        await self._queue.put({"content_type": "audio/pcm", "audio": "AAAA", "sample_rate": 24000})

    async def finish(self) -> None:
        await self._queue.put(None)

    async def close(self) -> None:
        await self._queue.put(None)

    async def chunks(self):
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item


@pytest.fixture
def voice(monkeypatch):
    """Wire the session to fakes. Returns a dict the test fills in."""
    state: dict = {"turns": [], "tts_texts": [], "answer": None}

    monkeypatch.setattr("app.services.voice_runtime.SessionLocal", lambda: DummySession())
    monkeypatch.setattr("app.services.voice_service.authorize_session", lambda *a, **k: "Maitri")
    monkeypatch.setattr("app.services.voice_service.voice_ready", lambda: True)

    async def fake_open_stt():
        return state["stt"]

    monkeypatch.setattr("app.services.sarvam_service.open_stt", fake_open_stt)

    async def slow_pcm_open(cancel=None):
        # A streaming TTS socket that never opens in time. The non-streamed
        # paths must release it without ending the session.
        await asyncio.Event().wait()

    monkeypatch.setattr("app.services.sarvam_service.open_pcm_tts", slow_pcm_open)

    async def fake_tts(text, cancel=None):
        state["tts_texts"].append(text)
        yield {"content_type": "audio/pcm", "audio": "AAAA"}

    monkeypatch.setattr("app.services.sarvam_service.stream_tts", fake_tts)

    def fake_answer(db, profile_id, question, history, *, public, claimed_profile_id=None, **extra):
        state["turns"].append(
            {
                "profile_id": profile_id,
                "question": question,
                "public": public,
                "claimed": claimed_profile_id,
                "history": [(t.role, t.content) for t in history],
            }
        )
        hook = state.get("during_agent")
        if hook is not None:
            hook(extra)
        answer = state.get("answer") or "She is an AI engineer."
        if isinstance(answer, Exception):
            raise answer
        return {
            "answer": answer,
            "intent": "knowledge",
            "contact_status": "none",
            "evidence_status": state.get("evidence_status", "evidence_available"),
            "sources": [],
            "summary": None,
        }

    monkeypatch.setattr("app.services.voice_service.answer_turn", fake_answer)
    return state


def run(ws: FakeBrowser, *, public: bool = False) -> None:
    asyncio.run(
        asyncio.wait_for(voice_runtime.run_live_session(ws, PROFILE_ID, public=public), timeout=10)
    )


# ── existing guarantees ──────────────────────────────────────────────────────


def test_public_session_rejects_private_profile(monkeypatch):
    ws = FakeBrowser(utterances=0)
    monkeypatch.setattr("app.services.voice_runtime.SessionLocal", lambda: DummySession())
    monkeypatch.setattr(
        "app.services.voice_service.authorize_session",
        lambda *a, **k: (_ for _ in ()).throw(
            HTTPException(status_code=404, detail="Profile not found.")
        ),
    )
    opened = []

    async def fake_open():
        opened.append(True)
        raise AssertionError("STT must not open for a rejected profile")

    monkeypatch.setattr("app.services.sarvam_service.open_stt", fake_open)
    asyncio.run(voice_runtime.run_live_session(ws, PROFILE_ID, public=True))
    assert opened == []
    assert any(m.get("type") == "error" for m in ws.sent)
    assert "not available" in ws.sent[0]["message"].lower()
    assert ws.closed


def test_final_transcript_invokes_agent_partial_does_not(voice):
    voice["stt"] = FakeStt(
        [[{"event": "transcript.partial", "text": "Tell me about"}, final("Tell me about Maitri.")]]
    )
    ws = FakeBrowser(utterances=1)
    run(ws)

    assert len(voice["turns"]) == 1
    assert voice["turns"][0]["profile_id"] == PROFILE_ID
    assert voice["turns"][0]["question"] == "Tell me about Maitri."
    assert voice["turns"][0]["claimed"] is None
    types = [m.get("type") for m in ws.sent]
    assert "partial" in types
    assert "final" in types
    assert "answer" in types
    assert "audio" in types
    audio = ws.of_type("audio")[0]
    assert audio["sample_rate"] == 24000
    assert audio["turn_id"] == 1


def test_tts_failure_is_safe(voice, monkeypatch):
    voice["stt"] = FakeStt([[final("Hello")]])

    async def boom(text, cancel=None):
        raise SarvamError("failed sk_secret_value_do_not_leak")
        yield  # pragma: no cover — keep this an async generator

    monkeypatch.setattr("app.services.sarvam_service.stream_tts", boom)
    monkeypatch.setattr(
        "app.services.sarvam_service.settings.SARVAM_API_KEY",
        "sk_secret_value_do_not_leak",
    )
    ws = FakeBrowser(utterances=1)
    run(ws)

    errors = ws.of_type("error")
    assert errors
    blob = str(errors)
    assert "sk_secret_value_do_not_leak" not in blob
    assert "Traceback" not in blob
    # No audio reached the browser, so the session returns straight to listening.
    complete = ws.of_type("turn_complete", 1)
    assert complete == [{"type": "turn_complete", "turn_id": 1, "awaiting_playback": False}]


# ── turn lifecycle regressions ───────────────────────────────────────────────


@pytest.mark.parametrize("public", [False, True])
def test_one_final_runs_the_agent_once(voice, public):
    voice["stt"] = FakeStt([[final("What projects has she worked on?")]])
    ws = FakeBrowser(utterances=1)
    run(ws, public=public)

    assert [t["question"] for t in voice["turns"]] == ["What projects has she worked on?"]
    assert voice["turns"][0]["public"] is public
    finals = [m for m in ws.of_type("answer", 1) if m.get("final")]
    assert len(finals) == 1
    assert len(ws.of_type("turn_complete", 1)) == 1


@pytest.mark.parametrize("public", [False, True])
def test_duplicate_final_runs_the_agent_once(voice, public):
    question = "What projects has she worked on?"
    voice["stt"] = FakeStt([[final(question), final(question)]])
    ws = FakeBrowser(utterances=1)
    run(ws, public=public)

    assert len(voice["turns"]) == 1
    assert len(ws.of_type("final")) == 1


def test_final_arriving_mid_turn_is_ignored(voice):
    """A stale final emitted while the agent is thinking never becomes a turn."""
    stt = FakeStt([[final("Tell me about MindMate.")]])
    voice["stt"] = stt
    holder: dict = {}

    def during_agent(_extra):
        # Runs in the agent's worker thread.
        holder["loop"].call_soon_threadsafe(stt.inject, final("Tell me about MindMate and"))

    voice["during_agent"] = during_agent
    ws = FakeBrowser(utterances=1)

    async def scenario():
        holder["loop"] = asyncio.get_running_loop()
        await voice_runtime.run_live_session(ws, PROFILE_ID, public=False)

    asyncio.run(asyncio.wait_for(scenario(), timeout=10))
    assert [t["question"] for t in voice["turns"]] == ["Tell me about MindMate."]


def test_final_after_turn_without_new_audio_is_ignored(voice):
    """Finals delivered after the turn but before the visitor spoke again are stale."""
    stt = FakeStt([[final("Tell me about MindMate.")]])
    voice["stt"] = stt
    ws = FakeBrowser(utterances=1)

    def react(payload, browser):
        if payload.get("type") == "turn_complete":
            stt.inject(final("Tell me about MindMate."))  # awaiting playback
        if payload.get("type") == "status" and payload.get("turn_id") == 1:
            stt.inject(final("Tell me about MindMate."))  # listening, no new audio

    ws.on_send = react
    run(ws)
    assert len(voice["turns"]) == 1


@pytest.mark.parametrize("public", [False, True])
def test_repeated_question_after_completed_turn_is_a_new_turn(voice, public):
    question = "What projects has she worked on?"
    voice["stt"] = FakeStt([[final(question)], [final(question)]])
    ws = FakeBrowser(utterances=2)
    run(ws, public=public)

    assert [t["question"] for t in voice["turns"]] == [question, question]
    assert [m["turn_id"] for m in ws.of_type("final")] == [1, 2]
    # The second turn sees the first as history.
    assert voice["turns"][1]["history"][0] == ("user", question)


def test_insufficient_evidence_gives_exactly_one_response(voice):
    """The 'I don't know' reply is spoken once and its echo is not a new turn."""
    voice["answer"] = INSUFFICIENT
    voice["evidence_status"] = "no_evidence"
    # Second utterance: the speakers' tail of the Rep's own reply reaches the mic.
    voice["stt"] = FakeStt(
        [[final("Does Maitri know PyTorch?")], [final("enough information in the profile to answer that")]],
        end_after_last=True,
    )
    ws = FakeBrowser(utterances=2)
    run(ws)

    assert len(voice["turns"]) == 1
    assert voice["tts_texts"] == [INSUFFICIENT]
    finals = [m for m in ws.of_type("answer") if m.get("final")]
    assert [m["text"] for m in finals] == [INSUFFICIENT]
    assert len(ws.of_type("turn_complete")) == 1


def test_tts_playback_does_not_create_a_user_turn(voice):
    """Microphone audio during THINKING/SPEAKING is never forwarded to STT."""
    stt = FakeStt([[final("Tell me about Maitri.")], [final("She is an AI engineer.")]])
    voice["stt"] = stt
    ws = FakeBrowser(utterances=1)

    def react(payload, browser):
        if payload.get("type") == "audio":
            browser.push({"type": "audio", "data": "ECHO"})  # speaker → mic

    ws.on_send = react
    run(ws)

    assert stt.audio == ["AAAA"]
    assert len(voice["turns"]) == 1


def test_interrupt_stops_playback_without_another_agent_call(voice, monkeypatch):
    async def slow_tts(text, cancel=None):
        voice["tts_texts"].append(text)
        yield {"content_type": "audio/pcm", "audio": "AAAA"}
        for _ in range(100):
            if cancel is not None and cancel.is_set():
                return
            await asyncio.sleep(0.005)
        yield {"content_type": "audio/pcm", "audio": "BBBB"}

    monkeypatch.setattr("app.services.sarvam_service.stream_tts", slow_tts)
    voice["stt"] = FakeStt([[final("Tell me about Maitri.")], [final("What did she build?")]])
    ws = FakeBrowser(utterances=2)
    interrupted_at: list[int] = []

    def react(payload, browser):
        if payload.get("type") == "audio" and payload.get("turn_id") == 1 and not interrupted_at:
            interrupted_at.append(len(browser.sent))
            browser.push({"type": "interrupt", "turn_id": 1})

    ws.on_send = react
    run(ws)

    assert [t["question"] for t in voice["turns"]] == ["Tell me about Maitri.", "What did she build?"]
    after = ws.sent[interrupted_at[0]:]
    assert not [m for m in after if m.get("turn_id") == 1 and m.get("type") in {"audio", "answer", "turn_complete"}]
    assert not any(m.get("data") == "BBBB" and m.get("turn_id") == 1 for m in ws.sent)
    # The visitor saw turn 1's answer, so it stays as context for turn 2.
    assert ("user", "Tell me about Maitri.") in voice["turns"][1]["history"]


def test_stale_interrupt_and_playback_done_are_ignored(voice):
    voice["stt"] = FakeStt([[final("Tell me about Maitri.")], [final("What did she build?")]])
    ws = FakeBrowser(utterances=2)

    def react(payload, browser):
        if payload.get("type") == "final" and payload["turn_id"] == 2:
            browser.push({"type": "interrupt", "turn_id": 1})
            browser.push({"type": "playback_done", "turn_id": 1})

    ws.on_send = react
    run(ws)

    assert len(voice["turns"]) == 2
    assert len(ws.of_type("turn_complete", 2)) == 1


def test_unused_tts_socket_does_not_end_the_session(voice):
    """Regression: cancelling a half-open TTS connect used to cancel the turn."""
    voice["stt"] = FakeStt([[final("Hello")], [final("Tell me more")]])
    ws = FakeBrowser(utterances=2)
    run(ws)

    assert len(voice["turns"]) == 2
    assert len([m for m in ws.of_type("answer") if m.get("final")]) == 2


def test_agent_error_is_one_response_then_next_turn_works(voice):
    voice["stt"] = FakeStt([[final("Hello")], [final("Tell me more")]])
    calls = {"n": 0}

    def during_agent(_extra):
        calls["n"] += 1
        voice["answer"] = (
            HTTPException(status_code=429, detail="quota") if calls["n"] == 1 else "Sure."
        )

    voice["during_agent"] = during_agent
    ws = FakeBrowser(utterances=2)
    run(ws)

    assert len(voice["turns"]) == 2
    assert "quota" in ws.of_type("error", 1)[0]["message"].lower()
    assert ws.of_type("answer", 2)[-1]["text"] == "Sure."
    # A failed turn is not conversation context.
    assert voice["turns"][1]["history"] == []


def test_streamed_sentences_speak_once_per_turn(voice, monkeypatch):
    pcm = FakePcm()

    async def open_pcm(cancel=None):
        return pcm

    monkeypatch.setattr("app.services.sarvam_service.open_pcm_tts", open_pcm)
    voice["stt"] = FakeStt([[final("Tell me about Maitri.")]])

    def during_agent(extra):
        extra["sentence_queue"].put("She builds AI systems.")
        extra["sentence_queue"].put("Mostly in Python.")

    voice["during_agent"] = during_agent
    voice["answer"] = "She builds AI systems. Mostly in Python."
    ws = FakeBrowser(utterances=1)
    run(ws)

    assert pcm.sentences == ["She builds AI systems.", "Mostly in Python."]
    assert voice["tts_texts"] == []  # non-streamed fallback not used
    assert len(ws.of_type("audio", 1)) == 2
    assert len(voice["turns"]) == 1


def test_missing_playback_done_falls_back_to_listening(voice):
    voice["stt"] = FakeStt([[final("Hello")], [final("Again")]])
    ws = FakeBrowser(utterances=2, playback_done=False)
    run(ws)
    assert len(voice["turns"]) == 2


def test_echo_check_compares_answer_not_question():
    answer = "She worked on Insightify, FlameCast and MindMate."
    assert voice_runtime.is_echo_of_answer("worked on Insightify FlameCast and MindMate", answer)
    assert not voice_runtime.is_echo_of_answer("What projects has she worked on?", answer)
    assert not voice_runtime.is_echo_of_answer("yes", answer)
