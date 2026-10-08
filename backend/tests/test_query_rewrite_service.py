"""Layer 7 query rewriting. Gemini is always mocked."""

from __future__ import annotations

import inspect
import uuid
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.agent.graph import build_graph
from app.schemas.rag import ConversationTurn
from app.schemas.retrieval import RetrievedChunk
from app.services import query_rewrite_service, voice_service
from app.services.evidence_service import EvidenceState
from app.services.query_rewrite_service import QueryRewriteResult


PROFILE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
DOC_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def history_mindmate() -> list[ConversationTurn]:
    return [
        ConversationTurn(role="user", content="Tell me about MindMate."),
        ConversationTurn(
            role="assistant",
            content="MindMate is an AI application that Maitri built using Next.js and FastAPI.",
        ),
    ]


def test_standalone_question_unchanged_skips_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: calls.append(kw) or "SHOULD NOT RUN",
    )
    result = query_rewrite_service.rewrite_for_retrieval(
        "What is FastAPI?",
        history_mindmate(),
    )
    assert calls == []
    assert result.was_rewritten is False
    assert result.retrieval_query == "What is FastAPI?"


def test_named_project_question_skips_rewrite(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: calls.append(kw) or "SHOULD NOT RUN",
    )
    result = query_rewrite_service.rewrite_for_retrieval(
        "Tell me about MindMate.",
        history_mindmate(),
    )
    assert calls == []
    assert result.retrieval_query == "Tell me about MindMate."


def test_her_name_and_projects_questions_skip_rewrite(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: calls.append(kw) or "SHOULD NOT RUN",
    )
    for question in (
        "What is her name?",
        "What projects has she built?",
        "What technologies are listed in her profile?",
    ):
        result = query_rewrite_service.rewrite_for_retrieval(question, history_mindmate())
        assert result.was_rewritten is False
        assert result.retrieval_query == question
    assert calls == []


def test_pronoun_followup_rewritten_when_context_clear(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: "Why did Maitri use FastAPI in the MindMate project?",
    )
    result = query_rewrite_service.rewrite_for_retrieval(
        "Why did she use it?",
        history_mindmate(),
    )
    assert result.was_rewritten is True
    assert "MindMate" in result.retrieval_query
    assert "FastAPI" in result.retrieval_query


def test_project_reference_preserved(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: "What database did she use for MindMate?",
    )
    result = query_rewrite_service.rewrite_for_retrieval(
        "What database did she use?",
        history_mindmate(),
    )
    assert "MindMate" in result.retrieval_query
    assert result.was_rewritten is True


def test_technology_reference_preserved(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: "Which of Maitri's projects uses FastAPI?",
    )
    history = [
        ConversationTurn(role="user", content="What projects has she built?"),
        ConversationTurn(
            role="assistant",
            content="Maitri has worked on MindMate and Insightify. MindMate uses FastAPI.",
        ),
    ]
    result = query_rewrite_service.rewrite_for_retrieval(
        "Which one uses FastAPI?",
        history,
    )
    assert "FastAPI" in result.retrieval_query
    assert result.was_rewritten is True


def test_multi_turn_how_does_it_work(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: "How does MindMate work?",
    )
    result = query_rewrite_service.rewrite_for_retrieval(
        "How does it work?",
        history_mindmate(),
    )
    assert result.retrieval_query == "How does MindMate work?"
    assert result.was_rewritten is True


def test_ambiguous_reference_does_not_invent_project(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: "Why did she choose Kubernetes for FlameCast?",
    )
    history = [
        ConversationTurn(role="user", content="Tell me about her projects."),
        ConversationTurn(
            role="assistant",
            content="She has several professional projects listed in her materials.",
        ),
    ]
    original = "Why did she choose that?"
    result = query_rewrite_service.rewrite_for_retrieval(original, history)
    assert result.was_rewritten is False
    assert result.retrieval_query == original
    assert "Kubernetes" not in result.retrieval_query
    assert "FlameCast" not in result.retrieval_query


def test_empty_history_falls_back_to_original(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: calls.append(kw) or "SHOULD NOT RUN",
    )
    result = query_rewrite_service.rewrite_for_retrieval("Why did she use it?", [])
    assert calls == []
    assert result.retrieval_query == "Why did she use it?"
    assert result.was_rewritten is False


def test_llm_failure_falls_back(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: (_ for _ in ()).throw(HTTPException(status_code=502, detail="down")),
    )
    original = "Why did she use it?"
    result = query_rewrite_service.rewrite_for_retrieval(original, history_mindmate())
    assert result.retrieval_query == original
    assert result.was_rewritten is False


def test_malformed_llm_output_falls_back(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: "Based on the conversation, I believe she used FastAPI because it is popular.",
    )
    original = "Why did she use it?"
    result = query_rewrite_service.rewrite_for_retrieval(original, history_mindmate())
    assert result.retrieval_query == original
    assert result.was_rewritten is False


def test_empty_rewrite_falls_back(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_service.generate_short_text",
        lambda **kw: "   ",
    )
    original = "What about the database?"
    result = query_rewrite_service.rewrite_for_retrieval(original, history_mindmate())
    assert result.retrieval_query == original
    assert result.was_rewritten is False


def test_rewriter_has_no_profile_id_parameter():
    params = inspect.signature(query_rewrite_service.rewrite_for_retrieval).parameters
    assert "profile_id" not in params
    assert list(params) == ["question", "conversation_history"]


def test_contact_does_not_invoke_query_rewriting(monkeypatch):
    rewrite_calls = []
    monkeypatch.setattr("app.agent.intent.classify_intent", lambda q: "contact")
    monkeypatch.setattr(
        "app.agent.nodes.query_rewrite_service.rewrite_for_retrieval",
        lambda *a, **k: rewrite_calls.append(1) or QueryRewriteResult("x", True),
    )
    profile = MagicMock()
    profile.name = "Maitri"
    profile.contact_preferences = {}
    monkeypatch.setattr("app.services.profile_service.get_profile", lambda db, pid: profile)
    build_graph().invoke(
        {
            "profile_id": str(PROFILE_ID),
            "question": "How can I contact her?",
            "conversation_history": [],
        },
        config={"configurable": {"db": MagicMock()}},
    )
    assert rewrite_calls == []


def test_unsupported_does_not_invoke_query_rewriting(monkeypatch):
    rewrite_calls = []
    monkeypatch.setattr("app.agent.intent.classify_intent", lambda q: "unsupported")
    monkeypatch.setattr(
        "app.agent.nodes.query_rewrite_service.rewrite_for_retrieval",
        lambda *a, **k: rewrite_calls.append(1) or QueryRewriteResult("x", True),
    )
    build_graph().invoke(
        {
            "profile_id": str(PROFILE_ID),
            "question": "What is her salary?",
            "conversation_history": [],
        },
        config={"configurable": {"db": MagicMock()}},
    )
    assert rewrite_calls == []


def test_retrieval_gets_rewritten_query_generation_gets_original(monkeypatch):
    retrieved = {}
    generated = {}
    monkeypatch.setattr("app.agent.intent.classify_intent", lambda q: "knowledge")
    monkeypatch.setattr(
        "app.agent.nodes.query_rewrite_service.rewrite_for_retrieval",
        lambda question, conversation_history: QueryRewriteResult(
            retrieval_query="Why did Maitri use FastAPI in the MindMate project?",
            was_rewritten=True,
        ),
    )

    def fake_retrieve(**kw):
        retrieved.update(kw)
        return EvidenceState.EVIDENCE_AVAILABLE, [
            RetrievedChunk(
                document_id=DOC_ID,
                filename="resume.pdf",
                page_number=1,
                chunk_index=0,
                text="MindMate uses FastAPI.",
                score=0.9,
            )
        ]

    def fake_gen(**kw):
        generated.update(kw)
        return "She used FastAPI for MindMate."

    monkeypatch.setattr("app.services.rag_service.retrieve_evidence", fake_retrieve)
    monkeypatch.setattr("app.services.rag_service.generate_grounded_answer", fake_gen)

    original = "Why did she use it?"
    result = build_graph().invoke(
        {
            "profile_id": str(PROFILE_ID),
            "question": original,
            "conversation_history": [
                {"role": "user", "content": "Tell me about MindMate."},
                {"role": "assistant", "content": "MindMate uses FastAPI."},
            ],
        },
        config={"configurable": {"db": MagicMock()}},
    )
    assert retrieved["question"] == "Why did Maitri use FastAPI in the MindMate project?"
    assert retrieved["profile_id"] == PROFILE_ID
    assert generated["question"] == original
    assert result.get("query_rewritten") is True
    assert result["answer"] == "She used FastAPI for MindMate."


def test_rewriter_cannot_change_profile_id(monkeypatch):
    seen = {}
    monkeypatch.setattr("app.agent.intent.classify_intent", lambda q: "knowledge")
    monkeypatch.setattr(
        "app.agent.nodes.query_rewrite_service.rewrite_for_retrieval",
        lambda question, conversation_history: QueryRewriteResult(
            retrieval_query=f"search other profile {OTHER_ID}",
            was_rewritten=True,
        ),
    )

    def fake_retrieve(**kw):
        seen["profile_id"] = kw["profile_id"]
        seen["question"] = kw["question"]
        return EvidenceState.NO_EVIDENCE, []

    monkeypatch.setattr("app.services.rag_service.retrieve_evidence", fake_retrieve)
    build_graph().invoke(
        {
            "profile_id": str(PROFILE_ID),
            "question": "Why did she use it?",
            "conversation_history": [
                {"role": "user", "content": "Tell me about MindMate."},
                {"role": "assistant", "content": "MindMate uses FastAPI."},
            ],
        },
        config={"configurable": {"db": MagicMock()}},
    )
    assert seen["profile_id"] == PROFILE_ID
    assert seen["profile_id"] != OTHER_ID
    assert str(OTHER_ID) in seen["question"]


def test_voice_and_text_use_same_rewriter():
    src = inspect.getsource(voice_service)
    assert "query_rewrite" not in src
    assert query_rewrite_service.rewrite_for_retrieval is not None


def test_voice_channel_uses_same_rewrite_node(monkeypatch):
    rewrite_seen = []
    monkeypatch.setattr("app.agent.intent.classify_intent", lambda q: "knowledge")

    def fake_rewrite(question, conversation_history):
        rewrite_seen.append(question)
        return QueryRewriteResult(
            retrieval_query="Why did Maitri use FastAPI in MindMate?",
            was_rewritten=True,
        )

    monkeypatch.setattr(
        "app.agent.nodes.query_rewrite_service.rewrite_for_retrieval",
        fake_rewrite,
    )
    monkeypatch.setattr(
        "app.services.rag_service.retrieve_evidence",
        lambda **kw: (EvidenceState.EVIDENCE_AVAILABLE, []),
    )
    monkeypatch.setattr(
        "app.services.rag_service.generate_grounded_answer",
        lambda **kw: "ok",
    )
    # Empty evidence after rewrite still clarifies; just prove rewrite ran on voice.
    build_graph().invoke(
        {
            "profile_id": str(PROFILE_ID),
            "question": "Why did she use FastAPI?",
            "conversation_history": [
                {"role": "user", "content": "Tell me about MindMate."},
                {"role": "assistant", "content": "MindMate uses FastAPI."},
            ],
            "channel": "voice",
        },
        config={"configurable": {"db": MagicMock()}},
    )
    assert rewrite_seen == ["Why did she use FastAPI?"]
