"""
evidence_service.py — Deterministic evidence assessment and context control (Layer 2.8).

Responsibilities (ONLY these):
  - Deduplicate retrieved chunks by identity (document_id, chunk_index)
  - Assess evidence quality: is there anything usable? is it relevant enough?
  - Apply a character budget so the context sent to Gemini stays bounded
  - Quote a short verbatim excerpt for the private evidence card

Does NOT know about:
  - Gemini, Qdrant, MySQL, or HTTP
  - Profile ownership or isolation
  - The question being asked (except for choosing which sentence to quote)

Design rationale
----------------
Retrieval returns ranked candidates. This service acts as a filter between
raw retrieval results and the generation layer, giving the system a clear,
testable policy for when generation is justified.

SCORE ≠ TRUTH
-------------
A cosine similarity score describes how semantically close a chunk is to the
query vector. It does NOT confirm or deny the factual accuracy of the chunk's
content. High score means "this chunk is topically similar to the query" —
nothing more.

Score semantics for Gemini Embedding 2 + COSINE in Qdrant:
  - Vectors are L2-normalised (768-dim Matryoshka truncation)
  - Qdrant returns cosine similarity directly as the score: ∈ [-1, 1]
  - In practice scores are in [0, 1] for semantically related pairs
  - Score ≥ 0.7 = strong topical match
  - Score ≈ 0.5 = moderate relevance
  - Score < 0.4 = questionable relevance

The default RAG_MIN_SCORE = 0.0 disables threshold filtering entirely,
preserving Layer 2.7 behavior. Operators should tune this value after
observing their actual score distribution with real documents.

Configuring RAG_MIN_SCORE:
  - 0.0   → disabled (all non-empty chunks pass)
  - 0.4   → conservative (only clearly relevant chunks pass)
  - 0.6   → strict (only strong matches pass)
  Caution: very high thresholds can cause false NO_EVIDENCE responses when
  evidence exists but uses different wording than the query.
"""

import re
from enum import Enum

from app.core.config import settings
from app.schemas.retrieval import RetrievedChunk


class EvidenceState(Enum):
    """
    Outcome of the evidence assessment step.

    NO_EVIDENCE
        Zero chunks were retrieved, or all retrieved chunks have empty/whitespace
        text that cannot be used as evidence.
        → Return insufficient-information response. Do not call Gemini.

    WEAK_EVIDENCE
        Chunks were retrieved with non-empty text, but all of them score below
        RAG_MIN_SCORE. The system has candidates, but not confident enough to
        justify a grounded generation.
        → Return insufficient-information response. Do not call Gemini.
        This state only triggers when RAG_MIN_SCORE > 0.0.

    EVIDENCE_AVAILABLE
        At least one chunk passed both the usability check (non-empty text) and
        the score threshold (if configured). Generation is justified.
        → Call Gemini with the filtered, deduplicated, budget-bounded chunks.
    """

    NO_EVIDENCE = "no_evidence"
    WEAK_EVIDENCE = "weak_evidence"
    EVIDENCE_AVAILABLE = "evidence_available"


def deduplicate_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """
    Remove duplicate retrieved chunks, keeping the highest-ranked occurrence.

    Identity is defined as (document_id, chunk_index). Qdrant's deterministic
    point IDs make true duplicates unlikely under normal operation, but
    overlapping chunk windows or repeated re-indexing can produce them.

    Chunks are expected to be in descending relevance order (Qdrant default).
    The first occurrence is always kept, which preserves the best-scored copy.

    Args:
        chunks: Retrieved chunks in descending relevance order.

    Returns:
        Deduplicated list in the same order, first occurrence wins.
    """
    seen: set[tuple] = set()
    result: list[RetrievedChunk] = []
    for chunk in chunks:
        key = (chunk.document_id, chunk.chunk_index)
        if key not in seen:
            seen.add(key)
            result.append(chunk)
    return result


def assess_evidence(
    chunks: list[RetrievedChunk],
) -> tuple[EvidenceState, list[RetrievedChunk]]:
    """
    Assess the quality and usability of retrieved chunks.

    Assessment steps:
    1. Filter out chunks whose text is empty or whitespace-only — these have
       no evidence value regardless of score.
    2. If no usable chunks remain → NO_EVIDENCE.
    3. If RAG_MIN_SCORE > 0.0 and all usable chunks score below it →
       WEAK_EVIDENCE with an empty accepted list.
    4. If RAG_MIN_SCORE > 0.0 and some chunks pass → EVIDENCE_AVAILABLE with
       only the above-threshold chunks.
    5. If RAG_MIN_SCORE = 0.0 (default) → EVIDENCE_AVAILABLE with all usable
       chunks (threshold filtering disabled).

    IMPORTANT: This function returns a state and a list of chunks that are
    safe to pass to generation. Do not pass WEAK_EVIDENCE or NO_EVIDENCE
    chunks to Gemini — they are either empty or insufficiently relevant.

    Args:
        chunks: Retrieved chunks after deduplication.

    Returns:
        (EvidenceState, accepted_chunks)
        - For NO_EVIDENCE:        (NO_EVIDENCE, [])
        - For WEAK_EVIDENCE:      (WEAK_EVIDENCE, [])
        - For EVIDENCE_AVAILABLE: (EVIDENCE_AVAILABLE, non_empty_above_threshold_chunks)
    """
    usable = [c for c in chunks if c.text and c.text.strip()]

    if not usable:
        return EvidenceState.NO_EVIDENCE, []

    min_score = settings.RAG_MIN_SCORE
    if min_score > 0.0:
        above_threshold = [c for c in usable if c.score >= min_score]
        if not above_threshold:
            return EvidenceState.WEAK_EVIDENCE, []
        return EvidenceState.EVIDENCE_AVAILABLE, above_threshold

    return EvidenceState.EVIDENCE_AVAILABLE, usable


_EXCERPT_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.]*")
_EXCERPT_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_EXCERPT_STOPWORDS = frozenset(
    "the a an and or of to in on for with by is was are were be been it its this that "
    "she he her his they their what which who how why when where did does do has have "
    "had about from as at use used using".split()
)


def excerpt_for(text: str, question: str, answer: str, limit: int = 220) -> str:
    """
    Return a short verbatim quote from a chunk for the private evidence card.

    Picks the sentence sharing the most content words with the question and
    answer; falls back to the chunk's opening. Never rewrites the text.
    """
    body = " ".join((text or "").split())
    if not body:
        return ""
    wanted = {
        w.lower()
        for w in _EXCERPT_WORD_RE.findall(f"{question} {answer}")
        if w.lower() not in _EXCERPT_STOPWORDS and len(w) > 2
    }
    sentences = [s for s in _EXCERPT_SENTENCE_RE.split(body) if s.strip()]
    best = sentences[0] if sentences else body
    best_score = 0
    for sentence in sentences:
        score = len({w.lower() for w in _EXCERPT_WORD_RE.findall(sentence)} & wanted)
        if score > best_score:
            best, best_score = sentence, score
    if len(best) <= limit:
        return best
    return best[: limit - 1].rsplit(" ", 1)[0] + "…"


def apply_context_budget(
    chunks: list[RetrievedChunk],
    max_chars: int | None = None,
) -> list[RetrievedChunk]:
    """
    Limit the total evidence text passed to generation.

    Chunks are assumed to be in descending relevance order. The budget is
    enforced greedily: chunks are added in order until the next chunk would
    push the total over the limit, at which point we stop.

    This means:
      - The highest-ranked evidence is always retained first.
      - Chunks are never partially truncated (no mid-chunk splitting).
      - A single chunk larger than the budget will result in zero chunks being
        passed — callers should ensure individual chunk sizes are reasonable
        (the chunking layer enforces CHUNK_SIZE for this reason).

    Trade-off: stopping at first overflow is simpler and more predictable
    than skipping oversized chunks and checking smaller ones, at the cost of
    potentially discarding relevant smaller chunks that would have fitted.
    For the MVP with uniform CHUNK_SIZE, this is an acceptable trade-off.

    Args:
        chunks:    Evidence chunks in descending relevance order.
        max_chars: Character budget override. If None, uses RAG_MAX_CONTEXT_CHARS
                   from settings. 0 or negative means no limit (return all).

    Returns:
        The subset of chunks that fits within the budget, in original order.
    """
    if max_chars is None:
        max_chars = settings.RAG_MAX_CONTEXT_CHARS

    if max_chars <= 0:
        return list(chunks)

    result: list[RetrievedChunk] = []
    total = 0
    for chunk in chunks:
        chunk_len = len(chunk.text)
        if total + chunk_len > max_chars:
            break
        result.append(chunk)
        total += chunk_len
    return result
