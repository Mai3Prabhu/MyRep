"""
Layer 8 evaluation harness.

Runs the existing LangGraph against a fixture keyword corpus.
This is NOT live Qdrant retrieval and NOT production latency.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.schemas.rag import ConversationTurn
from app.services import agent_service, public_service
from tests.evaluation.cases import CASES, EvalCase
from tests.evaluation.corpus import PROFILE_A, PROFILE_B, fixture_search


@dataclass
class CaseResult:
    case: EvalCase
    passed_behavioral: bool | None
    passed_fixture_retrieval: bool | None
    failures: list[str] = field(default_factory=list)
    intent: str | None = None
    rewrite_applied: bool | None = None
    retrieval_query: str | None = None
    evidence_status: str | None = None
    retrieved_chunk_count: int = 0
    relevant_chunk_found: bool | None = None
    profile_isolation_passed: bool | None = None
    public_isolation_passed: bool | None = None
    contact_status: str | None = None
    harness_total_latency_ms: int = 0
    answer: str = ""


@dataclass
class EvalReport:
    results: list[CaseResult]

    @property
    def total(self) -> int:
        return len(self.results)


def run_evaluation() -> EvalReport:
    return EvalReport(results=[_run_case(case) for case in CASES])


def format_report(report: EvalReport) -> str:
    behavioral = [r for r in report.results if r.passed_behavioral is not None]
    behavioral_pass = sum(1 for r in behavioral if r.passed_behavioral)
    retrieval = [r for r in report.results if r.passed_fixture_retrieval is not None]
    retrieval_pass = sum(1 for r in retrieval if r.passed_fixture_retrieval)
    expected_hits = [r for r in retrieval if r.case.expect_relevant_chunk is True]
    relevant = [r for r in expected_hits if r.relevant_chunk_found]
    rewrite_expected = [r for r in report.results if r.case.rewrite_expected is True]
    rewrite_ok = [
        r
        for r in rewrite_expected
        if r.passed_behavioral and (
            r.case.expected_entities == () or _entities_kept(r)
        )
    ]
    unsupported = [r for r in report.results if r.case.category == "UNSUPPORTED_FACT"]
    unsupported_ok = [r for r in unsupported if r.passed_behavioral]
    isolation = [r for r in report.results if r.case.category in {"PROFILE_ISOLATION", "PUBLIC_PROFILE_ISOLATION"}]
    isolation_ok = all(r.passed_behavioral for r in isolation) if isolation else False
    latencies = [r.harness_total_latency_ms for r in report.results]
    avg = statistics.mean(latencies) if latencies else 0
    p95 = _percentile(latencies, 95) if latencies else 0
    behavioral_fail = [r.case.case_id for r in behavioral if not r.passed_behavioral]
    fixture_fail = [r.case.case_id for r in retrieval if not r.passed_fixture_retrieval]

    lines = [
        "Evaluation Results",
        "------------------",
        "These sections are independent. Fixture retrieval is NOT Qdrant/Gemini",
        "production accuracy. Harness latency is NOT production latency or an SLO.",
        "",
        f"Total cases: {report.total}",
        "",
        "1) Behavioral / regression",
        f"   Passed: {behavioral_pass}/{len(behavioral)}",
        f"   Failed case ids: {behavioral_fail or 'none'}",
        f"   Unsupported questions correctly refused: {len(unsupported_ok)}/{len(unsupported)}",
        f"   Isolation (profile + public): {'PASS' if isolation_ok else 'FAIL'}",
        f"   Query rewriting expected: {len(rewrite_expected)}; "
        f"entity preservation / safe fallback: {len(rewrite_ok)}/{len(rewrite_expected)}",
        "",
        "2) Fixture-based retrieval baseline",
        "   Keyword overlap over a static corpus, filtered by profile_id.",
        "   NOT Qdrant cosine search. NOT production retrieval accuracy.",
        f"   Relevant evidence found (fixture): {len(relevant)}/{len(expected_hits)}",
        f"   Fixture retrieval passed: {retrieval_pass}/{len(retrieval)}",
        f"   Failed case ids: {fixture_fail or 'none'}",
        "",
        "3) Harness latency measurements",
        "   time.perf_counter around mocked graph invocations.",
        "   NOT production latency. NOT an SLO.",
        f"   Average total (harness): {avg:.1f} ms",
        f"   P95 total (harness): {p95:.1f} ms",
    ]
    return "\n".join(lines)


def _percentile(values: list[int], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return float(ordered[idx])


def _entities_kept(result: CaseResult) -> bool:
    query = result.retrieval_query or ""
    return all(entity.lower() in query.lower() for entity in result.case.expected_entities)


def _run_case(case: EvalCase) -> CaseResult:
    captured: dict = {
        "retrieval_query": None,
        "search_profile_id": None,
        "short_calls": 0,
        "gen_calls": 0,
        "retrieved_texts": [],
    }

    def fake_search(db, profile_id, query, top_k=5):
        captured["retrieval_query"] = query
        captured["search_profile_id"] = profile_id
        response = fixture_search(profile_id, query, top_k)
        captured["retrieved_texts"] = [item.text for item in response.results]
        return response

    def fake_short(*, system_instruction, prompt, max_output_tokens=80, temperature=0.0):
        captured["short_calls"] += 1
        return _fixture_rewrite(prompt)

    def fake_generate(
        question, evidence, conversation_history=None, channel="text", profile_facts=None
    ):
        captured["gen_calls"] += 1
        blob = " | ".join(chunk.text for chunk in evidence)
        # Saved profile facts route questions to generation even with zero
        # chunks. Model the system prompt's rule 3: when neither chunks nor
        # saved facts mention the question's subject, the model must refuse.
        if not evidence and not _facts_mention(question, profile_facts or ""):
            return "I don't have enough information in the available profile materials to answer that."
        return f"Grounded stub: {blob}"

    def fake_profile(db, profile_id):
        return _make_profile(profile_id)

    started = time.perf_counter()
    answer = ""
    intent = None
    evidence_status = None
    contact_status = None
    public_ok = None
    http_status = None

    patches = [
        patch("app.services.search_service.search_profile", fake_search),
        patch("app.services.generation_service.generate_short_text", fake_short),
        patch("app.services.generation_service.generate_answer", fake_generate),
        patch("app.services.profile_service.get_profile", fake_profile),
        patch("app.agent.intent.classify_with_llm", lambda q: None),
    ]
    for p in patches:
        p.start()
    try:
        history = [
            ConversationTurn(role=turn["role"], content=turn["content"])
            for turn in case.history
        ]
        if case.public is not None:
            db = MagicMock()
            row = _make_profile(case.profile_id)
            row.is_public = bool(case.public and case.profile_id == PROFILE_A)
            db.get.return_value = row
            try:
                resp = public_service.ask_public_profile(
                    db=db,
                    profile_id=case.profile_id,
                    question=case.question,
                    conversation_history=history,
                    channel=case.channel,
                )
                answer = resp.answer
                intent = resp.intent
                evidence_status = resp.evidence_status.value
                contact_status = resp.contact_status
                public_ok = True
            except HTTPException as exc:
                http_status = exc.status_code
                public_ok = exc.status_code == 404 and case.public is False
                answer = str(exc.detail)
        else:
            resp = agent_service.handle_question(
                db=MagicMock(),
                profile_id=case.profile_id,
                question=case.question,
                conversation_history=history,
                channel=case.channel,
            )
            answer = resp.answer
            intent = resp.intent
            evidence_status = resp.evidence_status.value
            contact_status = resp.contact_status
    finally:
        for p in reversed(patches):
            p.stop()

    harness_ms = int((time.perf_counter() - started) * 1000)
    retrieval_query = captured["retrieval_query"] or case.question
    rewrite_applied = (
        _norm(retrieval_query) != _norm(case.question)
        if captured["retrieval_query"] is not None
        else False
    )
    texts = captured["retrieved_texts"]
    relevant = None
    if case.expect_relevant_chunk is True:
        relevant = _has_tags(texts, case.relevant_tags)
    elif case.expect_relevant_chunk is False:
        if case.relevant_tags:
            relevant = _has_tags(texts, case.relevant_tags)
        else:
            relevant = len(texts) > 0

    isolation_ok = None
    if case.isolation_other_profile is not None:
        isolation_ok = captured["search_profile_id"] == case.profile_id
        isolation_ok = isolation_ok and not any(
            bad.lower() in " ".join(texts).lower() for bad in case.forbidden_substrings
        )

    result = CaseResult(
        case=case,
        passed_behavioral=None,
        passed_fixture_retrieval=None,
        intent=intent,
        rewrite_applied=rewrite_applied,
        retrieval_query=retrieval_query,
        evidence_status=evidence_status,
        retrieved_chunk_count=len(texts),
        relevant_chunk_found=relevant,
        profile_isolation_passed=isolation_ok,
        public_isolation_passed=public_ok,
        contact_status=contact_status,
        harness_total_latency_ms=harness_ms,
        answer=answer,
    )
    result.failures = _score_behavioral(case, result, captured, http_status)
    if case.track_behavioral:
        result.passed_behavioral = not result.failures
    if case.track_fixture_retrieval:
        result.passed_fixture_retrieval, retrieval_fail = _score_fixture_retrieval(case, result)
        if retrieval_fail:
            result.failures.append(retrieval_fail)
    return result


def _score_behavioral(case: EvalCase, result: CaseResult, captured: dict, http_status) -> list[str]:
    failures: list[str] = []
    if case.public is False:
        if result.public_isolation_passed:
            return []
        failures.append(f"expected public 404, got status={http_status}")
        return failures
    if case.expected_intent and result.intent != case.expected_intent:
        failures.append(f"intent {result.intent} != {case.expected_intent}")
    if case.rewrite_expected is False and captured["short_calls"] > 0:
        failures.append("rewrite LLM was called for a standalone question")
    if case.rewrite_expected is False and result.rewrite_applied:
        failures.append("retrieval_query was rewritten unexpectedly")
    if case.expected_entities:
        missing = [e for e in case.expected_entities if e.lower() not in (result.retrieval_query or "").lower()]
        if missing:
            failures.append(f"rewrite missing entities {missing}")
    if case.expected_contact_status and result.contact_status != case.expected_contact_status:
        failures.append(f"contact_status {result.contact_status} != {case.expected_contact_status}")
    if case.expect_insufficient:
        lowered = result.answer.lower()
        if "enough information" not in lowered and "can't help" not in lowered and "cannot help" not in lowered:
            if "professional background" not in lowered:
                failures.append("expected insufficient/unsupported refusal")
    for banned in case.forbidden_substrings:
        blob = f"{result.answer} {result.retrieval_query} {' '.join(captured.get('retrieved_texts') or [])}"
        if banned.lower() in blob.lower():
            failures.append(f"forbidden substring leaked: {banned}")
    if case.isolation_other_profile is not None and not result.profile_isolation_passed:
        failures.append("profile isolation failed")
    if case.channel == "voice" and result.intent != case.expected_intent:
        failures.append("voice path did not use the same intent routing")
    if case.category == "CONFLICTING_EVIDENCE":
        lowered = result.answer.lower()
        if "fastapi" not in lowered or "flask" not in lowered:
            failures.append(
                "conflicting fixture chunks did not both reach generation (stub)"
            )
    return failures


def _score_fixture_retrieval(case: EvalCase, result: CaseResult) -> tuple[bool, str | None]:
    if case.expected_evidence_status and result.evidence_status != case.expected_evidence_status:
        return False, (
            f"[fixture retrieval] evidence_status {result.evidence_status} "
            f"!= {case.expected_evidence_status}"
        )
    if case.expect_relevant_chunk is True and not result.relevant_chunk_found:
        return False, "[fixture retrieval] expected relevant fixture chunk not found"
    if case.expect_relevant_chunk is False and result.relevant_chunk_found:
        return False, "[fixture retrieval] unexpected relevant fixture chunk"
    return True, None


def _fixture_rewrite(prompt: str) -> str:
    """Deterministic stand-in for Gemini rewrite. Not production rewrite quality."""
    current = prompt.split("Current question:")[-1].split("Retrieval query:")[0].strip()
    history = prompt.split("Conversation:")[-1].split("Current question:")[0]
    if "Why did she choose that?" in current:
        return current
    if "MindMate" in history and (
        "Why did she use it?" in current or "Why did she use FastAPI?" in current
    ):
        return "Why did Maitri use FastAPI in the MindMate project?"
    if "MindMate" in history and "What database did she use?" in current:
        return "What database did she use for MindMate?"
    return current


_STUB_STOPWORDS = frozenset(
    "what which who whom does did has have had she her his they their about tell with "
    "from that this there been were is are was the and for any".split()
)


def _facts_mention(question: str, facts: str) -> bool:
    """True when a content word of the question appears in the saved facts."""
    words = [w.strip("?.,!").lower() for w in question.split()]
    content = [w for w in words if len(w) > 3 and w not in _STUB_STOPWORDS]
    lowered = facts.lower()
    return any(w in lowered for w in content)


def _make_profile(profile_id):
    row = MagicMock()
    row.id = profile_id
    row.name = "Maitri" if profile_id == PROFILE_A else "Other Person"
    row.is_public = profile_id == PROFILE_A
    row.headline = "AI Engineer"
    row.about = "Builds AI systems."
    row.skills = ["Python"]
    row.experience = None
    row.projects = None
    row.education = None
    row.contact_preferences = {
        "phone": "555-0100",
        "email": "private@example.com",
        "public": {"linkedin": "https://linkedin.com/in/maitri"}
        if profile_id == PROFILE_A
        else {},
    }
    return row


def _has_tags(texts: list[str], tags: tuple[str, ...]) -> bool:
    blob = " ".join(texts).lower()
    return all(tag.lower() in blob for tag in tags)


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split()).rstrip("?.!")
