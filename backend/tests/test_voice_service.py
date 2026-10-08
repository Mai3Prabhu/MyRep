"""Layer 6 voice application-boundary tests. No live Sarvam calls."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.public import PublicAskResponse, PublicSourceReference
from app.schemas.rag import AskResponse, ConversationTurn, EvidenceStatus, SourceReference
from app.services import voice_service
from app.services.sarvam_service import public_error_message


PROFILE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
DOC_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def test_answer_turn_uses_agent_service_and_path_profile(monkeypatch):
    captured = {}

    def fake_handle(**kw):
        captured.update(kw)
        return AskResponse(
            question=kw["question"],
            answer="Grounded spoken answer.",
            sources=[
                SourceReference(
                    document_id=DOC_ID,
                    filename="resume.pdf",
                    page_number=1,
                    chunk_index=0,
                    score=0.9,
                )
            ],
            evidence_status=EvidenceStatus.EVIDENCE_AVAILABLE,
            intent="knowledge",
        )

    monkeypatch.setattr("app.services.voice_service.agent_service.handle_question", fake_handle)
    result = voice_service.answer_turn(
        MagicMock(),
        PROFILE_ID,
        "Tell me about Maitri.",
        [],
        public=False,
        claimed_profile_id=str(OTHER_ID),
    )
    assert captured["profile_id"] == PROFILE_ID
    assert captured["channel"] == "voice"
    assert captured["question"] == "Tell me about Maitri."
    assert result["answer"] == "Grounded spoken answer."
    assert "document_id" not in result["sources"][0]


def test_answer_turn_does_not_call_search_directly(monkeypatch):
    calls = {"handle": 0}

    def fake_handle(**kw):
        calls["handle"] += 1
        return AskResponse(
            question=kw["question"],
            answer="ok",
            sources=[],
            evidence_status=EvidenceStatus.NO_EVIDENCE,
            intent="knowledge",
        )

    monkeypatch.setattr("app.services.voice_service.agent_service.handle_question", fake_handle)
    voice_service.answer_turn(
        MagicMock(),
        PROFILE_ID,
        "What projects has she worked on?",
        [],
        public=False,
    )
    assert calls["handle"] == 1


def test_public_answer_rejects_private_profile(monkeypatch):
    monkeypatch.setattr(
        "app.services.voice_service.public_service.ask_public_profile",
        lambda **kw: (_ for _ in ()).throw(
            HTTPException(status_code=404, detail="Profile not found.")
        ),
    )
    with pytest.raises(HTTPException) as exc:
        voice_service.answer_turn(
            MagicMock(), PROFILE_ID, "Hello", [], public=True
        )
    assert exc.value.status_code == 404


def test_public_answer_sanitizes_sources(monkeypatch):
    def fake_ask(**kw):
        assert kw["profile_id"] == PROFILE_ID
        assert kw["channel"] == "voice"
        return PublicAskResponse(
            question=kw["question"],
            answer="She built MyRep.",
            sources=[PublicSourceReference(filename="resume.pdf", page_number=2)],
            evidence_status=EvidenceStatus.EVIDENCE_AVAILABLE,
            intent="knowledge",
        )

    monkeypatch.setattr("app.services.voice_service.public_service.ask_public_profile", fake_ask)
    result = voice_service.answer_turn(
        MagicMock(),
        PROFILE_ID,
        "What projects has she worked on?",
        [],
        public=True,
        claimed_profile_id=str(OTHER_ID),
    )
    src = result["sources"][0]
    assert set(src.keys()) == {"filename", "page_number"}
    assert str(DOC_ID) not in str(result)


def test_append_history_is_bounded(monkeypatch):
    monkeypatch.setattr("app.services.rag_service.settings.MAX_CONVERSATION_MESSAGES", 4)
    history: list[ConversationTurn] = []
    for i in range(10):
        history = voice_service.append_history(history, f"q{i}", f"a{i}")
    assert len(history) == 4
    assert history[-1].content == "a9"


def test_authorize_public_uses_public_gate(monkeypatch):
    monkeypatch.setattr(
        "app.services.voice_service.public_service.get_public_profile",
        lambda db, pid: (_ for _ in ()).throw(
            HTTPException(status_code=404, detail="Profile not found.")
        ),
    )
    with pytest.raises(HTTPException) as exc:
        voice_service.authorize_session(MagicMock(), PROFILE_ID, public=True)
    assert exc.value.status_code == 404


def test_sarvam_error_message_redacts_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.services.sarvam_service.settings.SARVAM_API_KEY",
        "sk_secret_value_do_not_leak",
    )
    msg = public_error_message(RuntimeError("failed sk_secret_value_do_not_leak 401"))
    assert "sk_secret_value_do_not_leak" not in msg
    assert "Voice service is temporarily unavailable." == msg


def test_voice_ready_false_without_key(monkeypatch):
    monkeypatch.setattr("app.services.sarvam_service.settings.SARVAM_API_KEY", "")
    assert voice_service.voice_ready() is False


def test_langgraph_reviver_patch_suppresses_allowed_objects_warning():
    import warnings

    from langchain_core.load.load import Reviver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    from app.agent import compat  # noqa: F401

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Reviver()
        JsonPlusSerializer()
    msgs = [str(w.message) for w in caught if "allowed_objects" in str(w.message)]
    assert msgs == []


def test_voice_module_has_no_second_rag_or_graph():
    import ast
    import inspect

    src = inspect.getsource(voice_service)
    tree = ast.parse(src)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    joined = " ".join(sorted(imported))
    assert "agent_service" in joined
    assert "public_service" in joined
    assert "VoiceGraph" not in src
    assert "VoiceRAG" not in src
    assert "search_service" not in joined
    assert "qdrant_service" not in joined
    assert "generate_grounded_answer" not in src


def test_voice_knowledge_uses_existing_graph_retrieve(monkeypatch):
    from app.schemas.retrieval import RetrievedChunk
    from app.services.evidence_service import EvidenceState

    retrieved = {}

    def fake_retrieve(**kw):
        retrieved.update(kw)
        return EvidenceState.EVIDENCE_AVAILABLE, [
            RetrievedChunk(
                document_id=DOC_ID,
                filename="resume.pdf",
                page_number=1,
                chunk_index=0,
                text="Built MyRep with FastAPI.",
                score=0.9,
            )
        ]

    monkeypatch.setattr(
        "app.services.agent_service.profile_service.get_profile",
        lambda db, pid: MagicMock(name="Maitri"),
    )
    monkeypatch.setattr("app.agent.intent.classify_intent", lambda q: "knowledge")
    monkeypatch.setattr("app.services.rag_service.retrieve_evidence", fake_retrieve)
    monkeypatch.setattr(
        "app.services.rag_service.generate_grounded_answer",
        lambda **kw: "She built MyRep with FastAPI.",
    )

    result = voice_service.answer_turn(
        MagicMock(),
        PROFILE_ID,
        "What projects has she worked on?",
        [],
        public=False,
        claimed_profile_id=str(OTHER_ID),
    )
    assert retrieved["profile_id"] == PROFILE_ID
    assert retrieved["question"] == "What projects has she worked on?"
    assert result["intent"] == "knowledge"
    assert result["answer"] == "She built MyRep with FastAPI."


def test_voice_contact_unconfirmed_does_not_create_request(monkeypatch):
    created = []
    profile = MagicMock()
    profile.name = "Maitri"
    profile.contact_preferences = {
        "public": {"linkedin": "https://linkedin.com/in/maitri"}
    }
    monkeypatch.setattr(
        "app.services.profile_service.get_profile",
        lambda db, pid: profile,
    )
    monkeypatch.setattr("app.agent.intent.classify_intent", lambda q: "contact")
    monkeypatch.setattr(
        "app.services.contact_service.create_contact_request",
        lambda **kw: created.append(kw) or {"status": "PENDING", "request_id": "x"},
    )

    result = voice_service.answer_turn(
        MagicMock(),
        PROFILE_ID,
        "How can I contact her?",
        [],
        public=False,
    )
    assert created == []
    assert result["intent"] == "contact"
    assert result["contact_status"] == "offered"


def test_voice_contact_confirmed_becomes_pending(monkeypatch):
    created = []
    profile = MagicMock()
    profile.name = "Maitri"
    profile.contact_preferences = {
        "public": {"linkedin": "https://linkedin.com/in/maitri"}
    }
    monkeypatch.setattr(
        "app.services.profile_service.get_profile",
        lambda db, pid: profile,
    )
    monkeypatch.setattr("app.agent.intent.classify_intent", lambda q: "contact")

    def fake_create(**kw):
        created.append(kw)
        return {"status": "PENDING", "request_id": "req-1"}

    monkeypatch.setattr(
        "app.services.contact_service.create_contact_request",
        fake_create,
    )

    history = [
        ConversationTurn(role="user", content="How can I contact her?"),
        ConversationTurn(
            role="assistant",
            content="Would you like me to record a contact request?",
        ),
    ]
    result = voice_service.answer_turn(
        MagicMock(),
        PROFILE_ID,
        "Yes.",
        history,
        public=False,
    )
    assert len(created) == 1
    assert created[0]["profile_id"] == PROFILE_ID
    assert result["contact_status"] == "pending"
    assert "hasn't been emailed" in result["answer"].lower()
    assert "delivered" in result["answer"].lower()
    assert "has been emailed" not in result["answer"].lower()


def test_sarvam_errors_never_include_secrets_or_tracebacks(monkeypatch):
    monkeypatch.setattr(
        "app.services.sarvam_service.settings.SARVAM_API_KEY",
        "sk_secret_value_do_not_leak",
    )
    msg = public_error_message(
        RuntimeError(
            "Traceback (most recent call last):\n  File secret.py\n"
            "failed sk_secret_value_do_not_leak 401"
        )
    )
    assert "sk_secret_value_do_not_leak" not in msg
    assert "Traceback" not in msg
    assert "secret.py" not in msg
    assert msg == "Voice service is temporarily unavailable."


def test_stream_tts_yields_audio_and_stops_on_final(monkeypatch):
    import asyncio
    import json

    from app.services import sarvam_service

    class FakeWs:
        def __init__(self):
            self.sent = []
            self._messages = [
                json.dumps(
                    {
                        "type": "audio",
                        "data": {"audio": "abc123", "content_type": "audio/mpeg"},
                    }
                ),
                json.dumps({"type": "event", "data": {"event_type": "final"}}),
            ]

        async def send(self, raw):
            self.sent.append(json.loads(raw))

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._messages:
                raise StopAsyncIteration
            return self._messages.pop(0)

        async def close(self):
            pass

    async def fake_connect(*_args, **_kwargs):
        return FakeWs()

    monkeypatch.setattr(
        "app.services.sarvam_service.settings.SARVAM_API_KEY",
        "test-key",
    )
    monkeypatch.setattr("app.services.sarvam_service.websockets.connect", fake_connect)

    async def collect():
        return [chunk async for chunk in sarvam_service.stream_tts("Hello there.")]

    chunks = asyncio.run(collect())
    assert chunks == [
        {"content_type": "audio/mpeg", "audio": "abc123", "sample_rate": 24000}
    ]
