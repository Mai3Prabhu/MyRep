"""
rag_service.py - RAG orchestration (Layers 2.7 / 2.8 / 3.6).

Full pipeline:

    question [+ optional rewritten retrieval query from the graph]
        |
    search_service.search_profile()    -- embed query + Qdrant retrieval
    (the graph may pass a rewritten retrieval_query; this service does not rewrite)
        |
    evidence_service.deduplicate_chunks()  -- remove (doc_id, chunk_index) dupes
        |
    evidence_service.assess_evidence()     -- usability + score threshold check
        |
    NO_EVIDENCE / WEAK_EVIDENCE  ->  insufficient-information response (Gemini NOT called)
        |
    evidence_service.apply_context_budget()  -- character-budget enforcement
        |
    generation_service.generate_answer()   -- grounded Gemini generation
    (history forwarded here as contextual reference, NOT as evidence)
        |
    AskResponse (answer + source provenance + evidence_status)

This layer delegates:
  - All retrieval to search_service (query embedding + Qdrant filter)
  - Evidence assessment to evidence_service (deterministic, no external calls)
  - All generation to generation_service (Gemini generate_content)
  - Profile validation to search_service (MySQL profile lookup)

Profile isolation guarantee:
    profile_id comes from the MySQL-validated path parameter and is passed
    directly to search_service. It is never derived from the question text.

Evidence state semantics:
    NO_EVIDENCE      -- zero usable chunks found; Gemini not called
    WEAK_EVIDENCE    -- chunks found but all below RAG_MIN_SCORE; Gemini not called
    EVIDENCE_AVAILABLE -- sufficient evidence; Gemini called with bounded context

Layer 3.6 conversation context:
    Conversation history is BOUNDED to MAX_CONVERSATION_MESSAGES most recent turns.
    It is passed to generation_service only -- not to retrieval.
    Previous assistant messages are NOT treated as authoritative evidence.
    History helps Gemini resolve pronouns and references; professional facts
    must still come from retrieved document chunks.

Sources in the response:
    Only chunks that were actually passed to Gemini (after deduplication and
    context budget) are reported as sources. This means the source list is an
    accurate account of what informed the answer.
"""

import logging
import time
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core import voice_timing
from app.core.request_context import get_request_id
from app.schemas.rag import AskResponse, ConversationTurn, EvidenceStatus, SourceReference
from app.services import evidence_service, generation_service, search_service
from app.services.evidence_service import EvidenceState

logger = logging.getLogger(__name__)

_INSUFFICIENT_INFORMATION = (
    "I don't have enough information in the available profile materials "
    "to answer that question."
)


def bound_conversation_history(
    conversation_history: list[ConversationTurn] | None,
) -> list[ConversationTurn]:
    """Keep only the most recent MAX_CONVERSATION_MESSAGES turns."""
    if not conversation_history:
        return []
    return list(conversation_history[-settings.MAX_CONVERSATION_MESSAGES:])


def retrieve_evidence(
    db: Session,
    profile_id: uuid.UUID,
    question: str,
) -> tuple[EvidenceState, list]:
    """
    Retrieve, deduplicate, assess, and budget evidence for a query string.

    `question` here is the retrieval query (original or rewritten by the graph).
    This function does not rewrite queries and does not read conversation history.
    profile_id is the MySQL-validated path value — never derived from the query text.
    """
    logger.info(
        "retrieval_started request_id=%s profile_id=%s query_len=%d",
        get_request_id(), profile_id, len(question),
    )
    voice_timing.mark("retrieval_start")
    started = time.perf_counter()

    retrieval = search_service.search_profile(
        db=db,
        profile_id=profile_id,
        query=question,
        top_k=settings.RETRIEVAL_TOP_K,
    )

    logger.info(
        "retrieval_completed request_id=%s profile_id=%s chunks=%d latency_ms=%d",
        get_request_id(), profile_id, len(retrieval.results),
        int((time.perf_counter() - started) * 1000),
    )

    voice_timing.mark("context_build_start")
    unique_chunks = evidence_service.deduplicate_chunks(retrieval.results)
    state, accepted_chunks = evidence_service.assess_evidence(unique_chunks)

    logger.info(
        "evidence_assessed request_id=%s profile_id=%s state=%s accepted=%d",
        get_request_id(), profile_id, state.value, len(accepted_chunks),
    )

    if state != EvidenceState.EVIDENCE_AVAILABLE:
        voice_timing.mark("context_build_end")
        voice_timing.mark("retrieval_end")
        return state, []

    bounded_chunks = evidence_service.apply_context_budget(accepted_chunks)
    voice_timing.mark("context_build_end")
    voice_timing.mark("retrieval_end")
    return state, bounded_chunks


def generate_grounded_answer(
    question: str,
    chunks: list,
    conversation_history: list[ConversationTurn] | None = None,
    channel: str = "text",
    profile_facts: str | None = None,
) -> str:
    """Call generation_service with already-assessed evidence. Does not retrieve."""
    logger.info(
        "generation_started request_id=%s evidence_chunks=%d total_chars=%d",
        get_request_id(),
        len(chunks), sum(len(c.text) for c in chunks),
    )
    voice_timing.mark("llm_start")
    started = time.perf_counter()
    try:
        answer = generation_service.generate_answer(
            question=question,
            evidence=chunks,
            conversation_history=conversation_history or None,
            channel=channel,
            profile_facts=profile_facts,
        )
    except Exception:
        logger.error(
            "generation_failed request_id=%s error_type=Exception success=false",
            get_request_id(),
        )
        raise
    voice_timing.mark("llm_complete")
    logger.info(
        "generation_completed request_id=%s answer_len=%d latency_ms=%d",
        get_request_id(),
        len(answer),
        int((time.perf_counter() - started) * 1000),
    )
    return answer


def insufficient_response(question: str, status: EvidenceStatus) -> AskResponse:
    return AskResponse(
        question=question,
        answer=_INSUFFICIENT_INFORMATION,
        sources=[],
        evidence_status=status,
    )


def sources_from_chunks(
    chunks: list,
    question: str | None = None,
    answer: str | None = None,
) -> list[SourceReference]:
    """
    Provenance for the chunks passed to generation.

    With question/answer, each source also carries a short verbatim excerpt.
    Excerpts are for private responses; public_service strips them.
    """
    with_excerpt = question is not None and answer is not None
    return [
        SourceReference(
            document_id=chunk.document_id,
            filename=chunk.filename,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            score=chunk.score,
            excerpt=(
                evidence_service.excerpt_for(chunk.text, question, answer) or None
                if with_excerpt
                else None
            ),
        )
        for chunk in chunks
    ]


def answer_question(
    db: Session,
    profile_id: uuid.UUID,
    question: str,
    conversation_history: list[ConversationTurn] | None = None,
) -> AskResponse:
    """
    Answer a question about a profile using retrieved evidence from Qdrant.

    Independently usable without LangGraph. The agent graph calls
    retrieve_evidence / generate_grounded_answer rather than duplicating this.
    """
    bounded_history = bound_conversation_history(conversation_history)

    state, bounded_chunks = retrieve_evidence(db, profile_id, question)

    if state == EvidenceState.NO_EVIDENCE:
        return insufficient_response(question, EvidenceStatus.NO_EVIDENCE)

    if state == EvidenceState.WEAK_EVIDENCE:
        return insufficient_response(question, EvidenceStatus.WEAK_EVIDENCE)

    answer = generate_grounded_answer(
        question=question,
        chunks=bounded_chunks,
        conversation_history=bounded_history or None,
    )

    return AskResponse(
        question=question,
        answer=answer,
        sources=sources_from_chunks(bounded_chunks),
        evidence_status=EvidenceStatus.EVIDENCE_AVAILABLE,
    )

