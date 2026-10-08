"""Deterministic conversation-summary digest. No model calls anywhere."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.schemas.public import PublicAskResponse, PublicSourceReference
from app.schemas.rag import AskResponse, EvidenceStatus, SourceReference
from app.services import agent_service, conversation_summary_service as summary, public_service
from app.services.evidence_service import excerpt_for

PROFILE = {
    "projects": [
        {"name": "MindMate", "tech": ["FastAPI", "Qdrant"]},
        {"name": "Insightify", "tech": "React, Node.js"},
        {"name": "FlameCast"},
    ],
    "experience": [{"company": "Acme Labs", "role": "Intern"}],
    "education": [{"institution": "State University"}],
    "skills": ["Python", {"name": "LangGraph"}],
}


def digest(question, answer, *, intent="knowledge", status="evidence_available"):
    entities, technologies = summary.build_vocabulary(**PROFILE)
    return summary.build_turn_summary(
        question=question,
        answer=answer,
        intent=intent,
        evidence_status=status,
        entity_vocabulary=entities,
        technology_vocabulary=technologies,
        exclude=["Maitri"],
    )


def test_vocabulary_reads_names_only():
    entities, technologies = summary.build_vocabulary(**PROFILE)
    assert entities == ["MindMate", "Insightify", "FlameCast", "Acme Labs", "State University"]
    assert technologies == ["FastAPI", "Qdrant", "React", "Node.js", "Python", "LangGraph"]


def test_projects_turn_lists_projects_mentioned_in_answer():
    d = digest(
        "What projects has Maitri worked on?",
        "She has worked on Insightify, FlameCast and MindMate.",
    )
    assert d.outcome == "answered"
    assert d.topics == ["Projects"]
    assert d.entities == ["Insightify", "FlameCast", "MindMate"]
    assert d.question == "What projects has Maitri worked on?"
    assert d.key_points == ["She has worked on Insightify, FlameCast and MindMate."]


def test_technology_from_answer_is_listed():
    d = digest(
        "Why did she use FastAPI?",
        "MindMate uses FastAPI for its backend because it needed async request handling.",
    )
    assert d.technologies == ["FastAPI"]
    assert d.entities == ["MindMate"]


def test_summary_never_adds_terms_absent_from_the_answer():
    d = digest("Tell me about MindMate.", "MindMate is a mental-health companion app.")
    # Qdrant is in the profile vocabulary but was not said in this turn.
    assert "Qdrant" not in d.technologies
    assert d.entities == ["MindMate"]


def test_insufficient_answer_contributes_nothing_but_the_question():
    d = digest(
        "Does Maitri know PyTorch?",
        "I don't have enough information to confirm that.",
        status="evidence_available",
    )
    assert d.outcome == "not_in_profile"
    assert d.question == "Does Maitri know PyTorch?"
    assert d.entities == [] and d.technologies == [] and d.key_points == []


def test_negated_sentence_does_not_list_its_terms():
    d = digest(
        "What was MindMate built with, and was it on Kubernetes?",
        "MindMate was built with FastAPI. There is no information about Kubernetes in the available materials.",
    )
    assert d.outcome == "answered"
    assert "Kubernetes" not in d.technologies
    assert d.technologies == ["FastAPI"]


def test_no_evidence_status_is_not_in_profile():
    d = digest("What awards has she won?", "I don't have enough information.", status="no_evidence")
    assert d.outcome == "not_in_profile"


def test_contact_and_unsupported_outcomes():
    assert digest("How can I contact her?", "You can reach Maitri at ...", intent="contact").outcome == "contact"
    assert digest("How can I contact her?", "x", intent="contact").topics == ["Contact"]
    assert digest("What is her salary?", "I can't help with that.", intent="unsupported").outcome == "declined"


def test_ordinary_words_do_not_match_acronym_technologies():
    d = digest("What did she build?", "The rest of the work was done in Python.")
    assert "REST" not in d.technologies
    assert d.technologies == ["Python"]


def test_person_name_is_excluded_from_entities():
    entities, technologies = summary.build_vocabulary(**PROFILE)
    d = summary.build_turn_summary(
        question="Who is Maitri?",
        answer="Maitri built MindMate.",
        intent="knowledge",
        evidence_status="evidence_available",
        entity_vocabulary=[*entities, "Maitri"],
        technology_vocabulary=technologies,
        exclude=["Maitri"],
    )
    assert d.entities == ["MindMate"]


def test_long_question_is_clipped():
    d = digest("Tell me " + "very " * 40 + "much", "MindMate.")
    assert len(d.question) <= 90


# ── wiring ──────────────────────────────────────────────────────────────────


def _profile_row():
    row = MagicMock()
    row.name = "Maitri"
    row.projects = PROFILE["projects"]
    row.experience = PROFILE["experience"]
    row.education = PROFILE["education"]
    row.skills = PROFILE["skills"]
    row.contact_preferences = {"phone": "555-0100", "public": {"email": "m@example.com"}}
    return row


def test_handle_question_attaches_summary_without_model_calls(monkeypatch):
    """The digest is built after the graph and needs no LLM."""
    pid = uuid.uuid4()
    monkeypatch.setattr("app.services.profile_service.get_profile", lambda db, p: _profile_row())

    class Graph:
        def invoke(self, state, config):
            return {
                "answer": "She worked on MindMate with FastAPI.",
                "intent": "knowledge",
                "evidence_status": "evidence_available",
                "source_references": [],
            }

    monkeypatch.setattr("app.services.agent_service.get_graph", lambda: Graph())
    response = agent_service.handle_question(db=None, profile_id=pid, question="What has she built?")
    assert response.summary is not None
    assert response.summary.entities == ["MindMate"]
    assert response.summary.technologies == ["FastAPI"]
    assert "555-0100" not in response.model_dump_json()


def test_summary_failure_never_fails_the_request(monkeypatch):
    pid = uuid.uuid4()
    monkeypatch.setattr("app.services.profile_service.get_profile", lambda db, p: _profile_row())
    monkeypatch.setattr(
        "app.services.conversation_summary_service.build_turn_summary",
        lambda **_: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    class Graph:
        def invoke(self, state, config):
            return {"answer": "Hi.", "intent": "knowledge", "evidence_status": "no_evidence"}

    monkeypatch.setattr("app.services.agent_service.get_graph", lambda: Graph())
    response = agent_service.handle_question(db=None, profile_id=pid, question="Hi")
    assert response.answer == "Hi."
    assert response.summary is None


# ── evidence excerpts: private only ─────────────────────────────────────────


def test_excerpt_quotes_the_most_relevant_sentence_verbatim():
    text = "Maitri studied at State University. MindMate uses FastAPI for its backend API. It has a React UI."
    quote = excerpt_for(text, "Why did she use FastAPI?", "FastAPI powers the MindMate backend.")
    assert quote == "MindMate uses FastAPI for its backend API."
    assert quote in text


def test_excerpt_is_bounded():
    quote = excerpt_for("word " * 200, "q", "a", limit=60)
    assert len(quote) <= 60


def test_public_response_never_carries_excerpts(monkeypatch):
    pid = uuid.uuid4()
    private = AskResponse(
        question="Why FastAPI?",
        answer="MindMate uses FastAPI.",
        sources=[
            SourceReference(
                document_id=uuid.uuid4(),
                filename="C:/storage/docs/mindmate.pdf",
                page_number=4,
                chunk_index=2,
                score=0.9,
                excerpt="Phone 555-0100. MindMate uses FastAPI.",
            )
        ],
        evidence_status=EvidenceStatus.EVIDENCE_AVAILABLE,
        summary=summary.build_turn_summary(
            question="Why FastAPI?",
            answer="MindMate uses FastAPI.",
            intent="knowledge",
            evidence_status="evidence_available",
        ),
    )
    monkeypatch.setattr("app.services.public_service._require_public_profile", lambda db, p: None)
    monkeypatch.setattr("app.services.agent_service.handle_question", lambda **_: private)

    public = public_service.ask_public_profile(db=None, profile_id=pid, question="Why FastAPI?")
    assert isinstance(public, PublicAskResponse)
    assert public.sources == [PublicSourceReference(filename="mindmate.pdf", page_number=4)]
    blob = public.model_dump_json()
    assert "555-0100" not in blob
    assert "excerpt" not in blob
    assert public.summary is not None and public.summary.technologies == ["FastAPI"]
