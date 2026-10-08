"""Deterministic Layer 8 evaluation cases. Fixture-based, not live production data."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from tests.evaluation.corpus import PROFILE_A, PROFILE_B


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    category: str
    question: str
    history: list[dict[str, str]] = field(default_factory=list)
    profile_id: uuid.UUID = PROFILE_A
    channel: str = "text"
    public: bool | None = None  # True/False for public gate; None = private handle_question
    expected_intent: str = "knowledge"
    rewrite_expected: bool | None = None
    expected_entities: tuple[str, ...] = ()
    expected_evidence_status: str | None = None
    expect_relevant_chunk: bool | None = None
    relevant_tags: tuple[str, ...] = ()
    forbidden_substrings: tuple[str, ...] = ()
    expected_contact_status: str | None = None
    expect_insufficient: bool = False
    isolation_other_profile: uuid.UUID | None = None
    track_fixture_retrieval: bool = False
    track_behavioral: bool = True


_MINDMATE_HISTORY = [
    {"role": "user", "content": "Tell me about MindMate."},
    {
        "role": "assistant",
        "content": "MindMate is an AI application that Maitri built using Next.js and FastAPI.",
    },
]

_PROJECTS_HISTORY = [
    {"role": "user", "content": "Tell me about her projects."},
    {
        "role": "assistant",
        "content": "She has several professional projects listed in her materials.",
    },
]


CASES: tuple[EvalCase, ...] = (
    EvalCase(
        "direct_projects",
        "DIRECT_FACTUAL",
        "What projects has Maitri built?",
        expected_intent="knowledge",
        rewrite_expected=False,
        expected_evidence_status="evidence_available",
        expect_relevant_chunk=True,
        relevant_tags=("mindmate", "projects"),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "direct_mindmate",
        "DIRECT_FACTUAL",
        "Tell me about MindMate.",
        expected_intent="knowledge",
        rewrite_expected=False,
        expected_evidence_status="evidence_available",
        expect_relevant_chunk=True,
        relevant_tags=("mindmate",),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "technical_fastapi_named",
        "TECHNICAL_FACTUAL",
        "Why did MindMate use FastAPI?",
        expected_intent="knowledge",
        rewrite_expected=False,
        expected_evidence_status="evidence_available",
        expect_relevant_chunk=True,
        relevant_tags=("fastapi", "mindmate"),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "followup_fastapi",
        "CONVERSATIONAL_FOLLOWUP",
        "Why did she use FastAPI?",
        history=_MINDMATE_HISTORY,
        expected_intent="knowledge",
        rewrite_expected=True,
        expected_entities=("MindMate", "FastAPI"),
        expected_evidence_status="evidence_available",
        expect_relevant_chunk=True,
        relevant_tags=("fastapi", "mindmate"),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "followup_why_it",
        "CONVERSATIONAL_FOLLOWUP",
        "Why did she use it?",
        history=_MINDMATE_HISTORY,
        expected_intent="knowledge",
        rewrite_expected=True,
        expected_entities=("MindMate", "FastAPI"),
        expected_evidence_status="evidence_available",
        expect_relevant_chunk=True,
        relevant_tags=("fastapi", "mindmate"),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "multiturn_database",
        "MULTI_TURN_ENTITY_REFERENCE",
        "What database did she use?",
        history=_MINDMATE_HISTORY,
        expected_intent="knowledge",
        rewrite_expected=True,
        expected_entities=("MindMate",),
        expected_evidence_status="evidence_available",
        expect_relevant_chunk=True,
        relevant_tags=("postgresql", "mindmate"),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "standalone_fastapi",
        "STANDALONE_QUERY",
        "What is FastAPI?",
        history=_MINDMATE_HISTORY,
        expected_intent="knowledge",
        rewrite_expected=False,
        expected_evidence_status="evidence_available",
        expect_relevant_chunk=True,
        relevant_tags=("fastapi",),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "standalone_named_project",
        "STANDALONE_QUERY",
        "Tell me about MindMate.",
        history=_MINDMATE_HISTORY,
        expected_intent="knowledge",
        rewrite_expected=False,
        expected_evidence_status="evidence_available",
        expect_relevant_chunk=True,
        relevant_tags=("mindmate",),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "ambiguous_that",
        "AMBIGUOUS_FOLLOWUP",
        "Why did she choose that?",
        history=_PROJECTS_HISTORY,
        expected_intent="knowledge",
        rewrite_expected=True,
        expected_entities=(),
        forbidden_substrings=("FlameCast", "Kubernetes", "Kafka"),
        track_fixture_retrieval=False,
    ),
    EvalCase(
        "unsupported_salary",
        "UNSUPPORTED_FACT",
        "What is her salary?",
        expected_intent="unsupported",
        expect_insufficient=True,
        forbidden_substrings=("yes", "$", "lakh"),
    ),
    EvalCase(
        "unsupported_negotiate",
        "UNSUPPORTED_FACT",
        "Can you negotiate her offer?",
        expected_intent="unsupported",
        expect_insufficient=True,
    ),
    EvalCase(
        "no_evidence_pytorch",
        "NO_EVIDENCE",
        "Has she deployed PyTorch models on Kubernetes?",
        expected_intent="knowledge",
        rewrite_expected=False,
        expected_evidence_status="no_evidence",
        expect_relevant_chunk=False,
        expect_insufficient=True,
        forbidden_substrings=("yes, she deployed pytorch",),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "no_evidence_awards",
        "NO_EVIDENCE",
        "What awards has she won for FlameCast?",
        expected_intent="knowledge",
        expected_evidence_status="no_evidence",
        expect_relevant_chunk=False,
        expect_insufficient=True,
        forbidden_substrings=("FlameCast uses Kafka",),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "conflicting_backend",
        "CONFLICTING_EVIDENCE",
        "What backend did MindMate use?",
        expected_intent="knowledge",
        rewrite_expected=False,
        expected_evidence_status="evidence_available",
        expect_relevant_chunk=True,
        relevant_tags=("backend", "mindmate"),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "contact_can_i",
        "CONTACT_REQUEST",
        "Can I contact her?",
        expected_intent="contact",
        expected_contact_status="offered",
        forbidden_substrings=("555-0100", "private@example.com", "emailed"),
    ),
    EvalCase(
        "contact_how",
        "CONTACT_REQUEST",
        "How can I contact her?",
        expected_intent="contact",
        expected_contact_status="offered",
        forbidden_substrings=("555-0100", "private@example.com"),
    ),
    EvalCase(
        "public_isolation_private_profile",
        "PUBLIC_PROFILE_ISOLATION",
        "Tell me about MindMate.",
        profile_id=PROFILE_B,
        public=False,
        expected_intent="knowledge",
        track_behavioral=True,
        track_fixture_retrieval=False,
    ),
    EvalCase(
        "public_isolation_no_private_contact",
        "PUBLIC_PROFILE_ISOLATION",
        "How can I contact her?",
        public=True,
        expected_intent="contact",
        expected_contact_status="offered",
        forbidden_substrings=("555-0100", "private@example.com"),
    ),
    EvalCase(
        "profile_isolation_a",
        "PROFILE_ISOLATION",
        "What projects has she built?",
        profile_id=PROFILE_A,
        expected_intent="knowledge",
        isolation_other_profile=PROFILE_B,
        forbidden_substrings=("FlameCast", "Kafka"),
        expect_relevant_chunk=True,
        relevant_tags=("mindmate",),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "profile_isolation_b",
        "PROFILE_ISOLATION",
        "What is FlameCast?",
        profile_id=PROFILE_B,
        expected_intent="knowledge",
        isolation_other_profile=PROFILE_A,
        forbidden_substrings=("MindMate", "FastAPI"),
        expect_relevant_chunk=True,
        relevant_tags=("flamecast",),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "voice_followup",
        "VOICE_PATH",
        "Why did she use FastAPI?",
        history=_MINDMATE_HISTORY,
        channel="voice",
        expected_intent="knowledge",
        rewrite_expected=True,
        expected_entities=("MindMate", "FastAPI"),
        expect_relevant_chunk=True,
        relevant_tags=("fastapi", "mindmate"),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "voice_unsupported",
        "VOICE_PATH",
        "What is her salary?",
        channel="voice",
        expected_intent="unsupported",
        expect_insufficient=True,
    ),
    EvalCase(
        "voice_same_agent_direct",
        "VOICE_PATH",
        "Tell me about MindMate.",
        channel="voice",
        expected_intent="knowledge",
        rewrite_expected=False,
        expect_relevant_chunk=True,
        relevant_tags=("mindmate",),
        track_fixture_retrieval=True,
    ),
    EvalCase(
        "rewrite_skip_what_is_fastapi",
        "STANDALONE_QUERY",
        "What is FastAPI?",
        expected_intent="knowledge",
        rewrite_expected=False,
        track_fixture_retrieval=True,
        expect_relevant_chunk=True,
        relevant_tags=("fastapi",),
    ),
    EvalCase(
        "skills_direct",
        "DIRECT_FACTUAL",
        "What skills are listed?",
        expected_intent="knowledge",
        rewrite_expected=False,
        expect_relevant_chunk=True,
        relevant_tags=("skills", "python"),
        track_fixture_retrieval=True,
    ),
)
