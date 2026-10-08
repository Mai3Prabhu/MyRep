"""
test_evidence_service.py — Unit tests for Layer 2.8 evidence control service.

No external services are involved — evidence_service is pure Python.

Tests cover:

  --- deduplicate_chunks ---
  1.  Empty input returns empty list.
  2.  Non-duplicate chunks are returned unchanged, in original order.
  3.  Exact duplicate (same doc_id + chunk_index): only first occurrence kept.
  4.  Multiple duplicates across different doc_ids: each identity deduped.
  5.  Same document_id, different chunk_index → NOT duplicates (both kept).
  6.  Different document_id, same chunk_index → NOT duplicates (both kept).
  7.  First occurrence (highest rank) is preserved, not the later one.

  --- assess_evidence ---
  8.  Empty chunk list → NO_EVIDENCE, empty accepted list.
  9.  All chunks have whitespace-only text → NO_EVIDENCE, empty accepted list.
  10. Single chunk with valid text and RAG_MIN_SCORE=0.0 → EVIDENCE_AVAILABLE.
  11. RAG_MIN_SCORE=0.0 (default): all non-empty chunks pass regardless of score.
  12. All chunks score below RAG_MIN_SCORE → WEAK_EVIDENCE, empty accepted list.
  13. Some chunks above threshold, some below → EVIDENCE_AVAILABLE with only above.
  14. Mixed empty/non-empty text: empty text chunks are filtered out.
  15. EVIDENCE_AVAILABLE accepted list excludes whitespace-only chunks.
  16. assess_evidence does NOT modify the original list.

  --- apply_context_budget ---
  17. Empty input returns empty list.
  18. All chunks fit within budget → all returned.
  19. Budget exceeded at second chunk → only first chunk returned.
  20. max_chars=0 (disabled) → all chunks returned.
  21. Negative max_chars (disabled) → all chunks returned.
  22. Single chunk exactly at budget limit → returned.
  23. Single chunk one character over budget → NOT returned.
  24. Budget preserves original order (highest-ranked first).
  25. Context budget does not partially truncate chunk text.
"""

import uuid

import pytest

from app.schemas.retrieval import RetrievedChunk
from app.services import evidence_service
from app.services.evidence_service import EvidenceState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_DOC_ID_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SAMPLE_DOC_ID_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def make_chunk(
    doc_id: uuid.UUID = SAMPLE_DOC_ID_A,
    chunk_index: int = 0,
    text: str = "This is a relevant professional experience chunk.",
    score: float = 0.85,
    page_number: int = 1,
    filename: str = "resume.pdf",
) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=doc_id,
        filename=filename,
        page_number=page_number,
        chunk_index=chunk_index,
        text=text,
        score=score,
    )


# ---------------------------------------------------------------------------
# deduplicate_chunks — 1–7
# ---------------------------------------------------------------------------

def test_dedup_empty_input_returns_empty():
    assert evidence_service.deduplicate_chunks([]) == []


def test_dedup_no_duplicates_returns_all():
    chunks = [make_chunk(chunk_index=i) for i in range(3)]
    result = evidence_service.deduplicate_chunks(chunks)
    assert len(result) == 3


def test_dedup_preserves_original_order():
    chunks = [make_chunk(chunk_index=i, score=1.0 - i * 0.1) for i in range(3)]
    result = evidence_service.deduplicate_chunks(chunks)
    assert [c.chunk_index for c in result] == [0, 1, 2]


def test_dedup_removes_exact_duplicate():
    chunk_a = make_chunk(doc_id=SAMPLE_DOC_ID_A, chunk_index=0, text="First occurrence.", score=0.9)
    chunk_b = make_chunk(doc_id=SAMPLE_DOC_ID_A, chunk_index=0, text="Second occurrence.", score=0.7)
    result = evidence_service.deduplicate_chunks([chunk_a, chunk_b])
    assert len(result) == 1
    assert result[0].text == "First occurrence."


def test_dedup_keeps_first_occurrence():
    chunks = [
        make_chunk(doc_id=SAMPLE_DOC_ID_A, chunk_index=0, score=0.9),  # highest rank
        make_chunk(doc_id=SAMPLE_DOC_ID_A, chunk_index=0, score=0.6),  # duplicate — must be dropped
    ]
    result = evidence_service.deduplicate_chunks(chunks)
    assert len(result) == 1
    assert result[0].score == pytest.approx(0.9)


def test_dedup_different_chunk_index_same_doc_not_duplicate():
    chunk_0 = make_chunk(doc_id=SAMPLE_DOC_ID_A, chunk_index=0)
    chunk_1 = make_chunk(doc_id=SAMPLE_DOC_ID_A, chunk_index=1)
    result = evidence_service.deduplicate_chunks([chunk_0, chunk_1])
    assert len(result) == 2


def test_dedup_same_chunk_index_different_doc_not_duplicate():
    chunk_a = make_chunk(doc_id=SAMPLE_DOC_ID_A, chunk_index=0)
    chunk_b = make_chunk(doc_id=SAMPLE_DOC_ID_B, chunk_index=0)
    result = evidence_service.deduplicate_chunks([chunk_a, chunk_b])
    assert len(result) == 2


def test_dedup_multi_doc_duplicates_deduped_independently():
    """Two chunks from doc A and two from doc B: each pair should be deduped."""
    chunks = [
        make_chunk(doc_id=SAMPLE_DOC_ID_A, chunk_index=0, text="A0-first"),
        make_chunk(doc_id=SAMPLE_DOC_ID_B, chunk_index=0, text="B0-first"),
        make_chunk(doc_id=SAMPLE_DOC_ID_A, chunk_index=0, text="A0-second"),  # dup of A0
        make_chunk(doc_id=SAMPLE_DOC_ID_B, chunk_index=0, text="B0-second"),  # dup of B0
    ]
    result = evidence_service.deduplicate_chunks(chunks)
    assert len(result) == 2
    texts = {c.text for c in result}
    assert "A0-first" in texts
    assert "B0-first" in texts


# ---------------------------------------------------------------------------
# assess_evidence — 8–16
# ---------------------------------------------------------------------------

def test_assess_empty_list_returns_no_evidence(monkeypatch):
    monkeypatch.setattr("app.services.evidence_service.settings.RAG_MIN_SCORE", 0.0)
    state, accepted = evidence_service.assess_evidence([])
    assert state == EvidenceState.NO_EVIDENCE
    assert accepted == []


def test_assess_all_whitespace_text_returns_no_evidence(monkeypatch):
    monkeypatch.setattr("app.services.evidence_service.settings.RAG_MIN_SCORE", 0.0)
    chunks = [
        make_chunk(text="   "),
        make_chunk(text="\n\t"),
        make_chunk(text=""),
    ]
    state, accepted = evidence_service.assess_evidence(chunks)
    assert state == EvidenceState.NO_EVIDENCE
    assert accepted == []


def test_assess_valid_chunk_with_zero_threshold_returns_evidence_available(monkeypatch):
    monkeypatch.setattr("app.services.evidence_service.settings.RAG_MIN_SCORE", 0.0)
    chunks = [make_chunk(text="Valid professional content.", score=0.3)]
    state, accepted = evidence_service.assess_evidence(chunks)
    assert state == EvidenceState.EVIDENCE_AVAILABLE
    assert len(accepted) == 1


def test_assess_zero_threshold_passes_all_non_empty_regardless_of_score(monkeypatch):
    monkeypatch.setattr("app.services.evidence_service.settings.RAG_MIN_SCORE", 0.0)
    chunks = [
        make_chunk(score=0.1, text="Low score but valid."),
        make_chunk(score=0.05, text="Very low but still text."),
    ]
    state, accepted = evidence_service.assess_evidence(chunks)
    assert state == EvidenceState.EVIDENCE_AVAILABLE
    assert len(accepted) == 2


def test_assess_all_below_threshold_returns_weak_evidence(monkeypatch):
    monkeypatch.setattr("app.services.evidence_service.settings.RAG_MIN_SCORE", 0.6)
    chunks = [
        make_chunk(score=0.3, text="Below threshold chunk."),
        make_chunk(score=0.45, text="Also below threshold."),
    ]
    state, accepted = evidence_service.assess_evidence(chunks)
    assert state == EvidenceState.WEAK_EVIDENCE
    assert accepted == []


def test_assess_mixed_scores_returns_only_above_threshold(monkeypatch):
    monkeypatch.setattr("app.services.evidence_service.settings.RAG_MIN_SCORE", 0.5)
    chunks = [
        make_chunk(chunk_index=0, score=0.8, text="High relevance."),
        make_chunk(chunk_index=1, score=0.3, text="Low relevance."),
        make_chunk(chunk_index=2, score=0.6, text="Medium relevance."),
    ]
    state, accepted = evidence_service.assess_evidence(chunks)
    assert state == EvidenceState.EVIDENCE_AVAILABLE
    accepted_indices = [c.chunk_index for c in accepted]
    assert 0 in accepted_indices
    assert 2 in accepted_indices
    assert 1 not in accepted_indices


def test_assess_filters_empty_text_chunks(monkeypatch):
    monkeypatch.setattr("app.services.evidence_service.settings.RAG_MIN_SCORE", 0.0)
    chunks = [
        make_chunk(chunk_index=0, text="Valid evidence."),
        make_chunk(chunk_index=1, text="   "),
        make_chunk(chunk_index=2, text=""),
    ]
    state, accepted = evidence_service.assess_evidence(chunks)
    assert state == EvidenceState.EVIDENCE_AVAILABLE
    assert len(accepted) == 1
    assert accepted[0].chunk_index == 0


def test_assess_weak_evidence_returns_empty_accepted_list(monkeypatch):
    monkeypatch.setattr("app.services.evidence_service.settings.RAG_MIN_SCORE", 0.9)
    chunks = [make_chunk(score=0.5, text="Below strict threshold.")]
    state, accepted = evidence_service.assess_evidence(chunks)
    assert state == EvidenceState.WEAK_EVIDENCE
    assert accepted == []


def test_assess_does_not_mutate_input_list(monkeypatch):
    monkeypatch.setattr("app.services.evidence_service.settings.RAG_MIN_SCORE", 0.0)
    original = [make_chunk(chunk_index=i) for i in range(3)]
    original_ids = [id(c) for c in original]
    evidence_service.assess_evidence(original)
    assert [id(c) for c in original] == original_ids


# ---------------------------------------------------------------------------
# apply_context_budget — 17–25
# ---------------------------------------------------------------------------

def test_budget_empty_input_returns_empty(monkeypatch):
    result = evidence_service.apply_context_budget([], max_chars=1000)
    assert result == []


def test_budget_all_within_budget_returns_all():
    chunks = [make_chunk(chunk_index=i, text="Short.") for i in range(4)]
    result = evidence_service.apply_context_budget(chunks, max_chars=1000)
    assert len(result) == 4


def test_budget_stops_at_first_overflow():
    """Budget=10: first chunk fits (6 chars), second does not (6 more = 12 > 10)."""
    chunk_a = make_chunk(chunk_index=0, text="123456")  # 6 chars
    chunk_b = make_chunk(chunk_index=1, text="789012")  # 6 chars — would push to 12
    result = evidence_service.apply_context_budget([chunk_a, chunk_b], max_chars=10)
    assert len(result) == 1
    assert result[0].chunk_index == 0


def test_budget_zero_means_no_limit():
    chunks = [make_chunk(chunk_index=i, text="x" * 5000) for i in range(5)]
    result = evidence_service.apply_context_budget(chunks, max_chars=0)
    assert len(result) == 5


def test_budget_negative_means_no_limit():
    chunks = [make_chunk(chunk_index=i, text="x" * 5000) for i in range(3)]
    result = evidence_service.apply_context_budget(chunks, max_chars=-1)
    assert len(result) == 3


def test_budget_single_chunk_exactly_at_limit():
    chunk = make_chunk(text="A" * 100)
    result = evidence_service.apply_context_budget([chunk], max_chars=100)
    assert len(result) == 1


def test_budget_single_chunk_one_over_limit():
    chunk = make_chunk(text="A" * 101)
    result = evidence_service.apply_context_budget([chunk], max_chars=100)
    assert len(result) == 0


def test_budget_preserves_order():
    chunks = [make_chunk(chunk_index=i, text=f"Chunk {i} content.") for i in range(5)]
    result = evidence_service.apply_context_budget(chunks, max_chars=10000)
    assert [c.chunk_index for c in result] == [0, 1, 2, 3, 4]


def test_budget_does_not_truncate_chunk_text():
    """The text within a chunk must never be partially cut."""
    text = "Full chunk text that should never be truncated mid-sentence."
    chunk = make_chunk(text=text)
    # Budget exactly fits this chunk
    result = evidence_service.apply_context_budget([chunk], max_chars=len(text))
    assert len(result) == 1
    assert result[0].text == text


def test_budget_uses_settings_when_max_chars_not_provided(monkeypatch):
    monkeypatch.setattr("app.services.evidence_service.settings.RAG_MAX_CONTEXT_CHARS", 10)
    chunk_a = make_chunk(chunk_index=0, text="12345")   # 5 chars
    chunk_b = make_chunk(chunk_index=1, text="678901")  # 6 chars → 11 total > 10
    result = evidence_service.apply_context_budget([chunk_a, chunk_b])
    assert len(result) == 1
    assert result[0].chunk_index == 0
