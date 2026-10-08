"""Sentence streaming, quota fail-fast, and one-timeline TTS."""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core import voice_timing
from app.schemas.retrieval import RetrievedChunk
from app.services import generation_service, sarvam_service
from app.services.sentence_buffer import SentenceBuffer


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        document_id=uuid.uuid4(),
        filename="resume.pdf",
        page_number=1,
        chunk_index=0,
        text="Built MyRep.",
        score=0.9,
    )


class _Piece:
    def __init__(self, text: str):
        self.text = text


def test_chunks_join_into_one_sentence():
    buffer = SentenceBuffer()
    assert buffer.push("Hel") == []
    assert buffer.push("lo there. ") == ["Hello there."]
    assert buffer.flush() is None


def test_split_inside_a_sentence_waits():
    buffer = SentenceBuffer()
    assert buffer.push("She built ") == []
    assert buffer.push("MyRep with FastAPI. ") == ["She built MyRep with FastAPI."]


def test_multiple_sentences():
    buffer = SentenceBuffer()
    ready = buffer.push("Maitri is an engineer. She built MyRep. ")
    assert ready == ["Maitri is an engineer.", "She built MyRep."]


def test_long_clause_is_spoken_before_the_period():
    buffer = SentenceBuffer()
    text = (
        "Maitri Prabhu is an AI Engineer based in Bangalore, "
        "India, who focuses on building production systems"
    )
    ready = buffer.push(text)
    assert ready
    assert ready[0].endswith(",")
    assert "production systems" not in ready[0]
    assert "production systems" in (buffer.flush() or "")


def test_flush_keeps_text_without_punctuation():
    buffer = SentenceBuffer()
    assert buffer.push("She is an AI engineer") == []
    assert buffer.flush() == "She is an AI engineer"


def test_abbreviation_and_decimal_are_not_boundaries():
    buffer = SentenceBuffer()
    ready = buffer.push("Dr. Smith uses Python 3.5 daily. ")
    assert ready == ["Dr. Smith uses Python 3.5 daily."]


def _client(pieces: list[str]):
    client = MagicMock()
    client.models.generate_content_stream.return_value = iter(
        _Piece(piece) for piece in pieces
    )
    return client


def test_stream_yields_sentences_from_split_chunks(monkeypatch):
    monkeypatch.setattr(generation_service.settings, "GEMINI_API_KEY", "fake-key")
    voice_timing.begin()
    with patch("google.genai.Client", return_value=_client(["Hel", "lo there. ", "Done now"])):
        spoken = list(
            generation_service.iter_spoken_sentences("Who is she?", [_chunk()])
        )
    assert spoken == ["Hello there.", "Done now"]
    marks = voice_timing.snapshot()
    assert "llm_stream_start" in marks
    assert "llm_first_token" in marks
    assert "first_sentence_ready" in marks
    assert "llm_stream_complete" in marks
    assert marks["llm_first_token"] >= marks["llm_stream_start"]
    assert marks["first_sentence_ready"] >= marks["llm_first_token"]


def test_stream_stops_when_a_new_turn_cancels(monkeypatch):
    monkeypatch.setattr(generation_service.settings, "GEMINI_API_KEY", "fake-key")
    voice_timing.begin()
    flag = {"stop": False}

    def stop() -> bool:
        return flag["stop"]

    with patch(
        "google.genai.Client",
        return_value=_client(["Hello there. ", "This is the second sentence. "]),
    ):
        stream = generation_service.iter_spoken_sentences(
            "Who is she?",
            [_chunk()],
            should_stop=stop,
        )
        first = next(stream)
        flag["stop"] = True
        rest = list(stream)
    assert first == "Hello there."
    assert rest == []


def test_quota_429_does_not_sleep(monkeypatch):
    monkeypatch.setattr(generation_service.settings, "GEMINI_API_KEY", "fake-key")
    sleeps: list[float] = []
    monkeypatch.setattr(generation_service.time, "sleep", lambda seconds: sleeps.append(seconds))
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError(
        "429 RESOURCE_EXHAUSTED quota exceeded"
    )
    with patch("google.genai.Client", return_value=client):
        with pytest.raises(HTTPException) as exc:
            generation_service.generate_answer("question", [_chunk()])
    assert exc.value.status_code == 429
    assert "quota is exhausted" in exc.value.detail
    assert sleeps == []


def test_transient_503_still_retries(monkeypatch):
    monkeypatch.setattr(generation_service.settings, "GEMINI_API_KEY", "fake-key")
    sleeps: list[float] = []
    monkeypatch.setattr(generation_service.time, "sleep", lambda seconds: sleeps.append(seconds))
    client = MagicMock()
    ok = MagicMock()
    ok.text = "Grounded answer."
    client.models.generate_content.side_effect = [
        RuntimeError("503 UNAVAILABLE"),
        ok,
    ]
    with patch("google.genai.Client", return_value=client):
        text = generation_service.generate_answer("question", [_chunk()])
    assert text == "Grounded answer."
    assert sleeps == [1.5]


def test_cancel_discards_a_later_sentence_on_the_open_socket(monkeypatch):
    """After cancel, sentence 2 is not written. Sentence 1 already sent stays the only text."""

    class FakeWs:
        def __init__(self):
            self.sent: list[dict] = []
            self._incoming: asyncio.Queue = asyncio.Queue()

        async def send(self, raw):
            self.sent.append(json.loads(raw))

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self._incoming.get()

        async def close(self):
            return None

    async def fake_connect(*_args, **_kwargs):
        return FakeWs()

    monkeypatch.setattr(sarvam_service.settings, "SARVAM_API_KEY", "test-key")
    monkeypatch.setattr(sarvam_service.websockets, "connect", fake_connect)

    async def run():
        cancel = asyncio.Event()
        session = await sarvam_service.open_pcm_tts(cancel)
        await session.send_sentence("Sentence one is playing.")
        cancel.set()
        await session.send_sentence("Sentence two must not be sent.")
        texts = [item["data"]["text"] for item in session._ws.sent if item.get("type") == "text"]
        session._reader.cancel()
        try:
            await session._reader
        except asyncio.CancelledError:
            pass
        return texts

    assert asyncio.run(run()) == ["Sentence one is playing."]


def test_sentence_two_is_queued_after_sentence_one_on_one_socket(monkeypatch):
    """One Bulbul socket, texts in order, PCM chunks in that same order."""

    class FakeWs:
        def __init__(self):
            self.sent: list[dict] = []
            self._incoming: asyncio.Queue = asyncio.Queue()
            self.closed = False

        async def send(self, raw):
            message = json.loads(raw)
            self.sent.append(message)
            if message.get("type") == "flush":
                index = sum(1 for item in self.sent if item.get("type") == "flush")
                await self._incoming.put(
                    json.dumps(
                        {
                            "type": "audio",
                            "data": {"audio": f"pcm-{index}", "content_type": "audio/pcm"},
                        }
                    )
                )
                await self._incoming.put(
                    json.dumps({"type": "event", "data": {"event_type": "final"}})
                )

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.closed and self._incoming.empty():
                raise StopAsyncIteration
            return await self._incoming.get()

        async def recv(self):
            if self.closed and self._incoming.empty():
                raise ConnectionError
            return await self._incoming.get()

        async def close(self):
            self.closed = True

    sockets: list[FakeWs] = []

    async def fake_connect(*_args, **_kwargs):
        ws = FakeWs()
        sockets.append(ws)
        return ws

    monkeypatch.setattr(sarvam_service.settings, "SARVAM_API_KEY", "test-key")
    monkeypatch.setattr(sarvam_service.websockets, "connect", fake_connect)

    async def run():
        session = await sarvam_service.open_pcm_tts()
        heard: list[str] = []

        async def collect():
            async for chunk in session.chunks():
                heard.append(chunk["audio"])

        task = asyncio.create_task(collect())
        await session.send_sentence("Maitri is an engineer.")
        await session.send_sentence("She built MyRep.")
        for _ in range(30):
            await asyncio.sleep(0)
            if session._final_count >= 2:
                break
        await session.finish()
        await task
        return heard

    heard = asyncio.run(run())
    assert len(sockets) == 1
    texts = [item["data"]["text"] for item in sockets[0].sent if item.get("type") == "text"]
    assert texts == ["Maitri is an engineer.", "She built MyRep."]
    assert sum(1 for item in sockets[0].sent if item.get("type") == "config") == 1
    assert heard == ["pcm-1", "pcm-2"]

    # Same rule as VoicePanel schedulePcm: the next buffer starts at the playhead.
    playhead = 0.0
    starts = []
    for duration, now in ((1.2, 0.0), (0.8, 0.3)):
        start = max(now + 0.05, playhead or now + 0.05)
        playhead = start + duration
        starts.append(start)
    assert starts[1] >= starts[0] + 1.2
