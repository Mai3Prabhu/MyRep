"""
Schemas for the RAG question-answering endpoint (Layers 2.7 / 2.8 / 3.6).
"""

import uuid
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class EvidenceStatus(str, Enum):
    """
    Outcome of the evidence assessment step (Layer 2.8).

    Included in AskResponse so API consumers can distinguish the reason for
    an "insufficient information" answer without parsing the message text.

    no_evidence
        Qdrant returned no chunks, or all chunks had empty text.
        Gemini was not called.

    weak_evidence
        Chunks were found but all scored below RAG_MIN_SCORE.
        Gemini was not called.
        Only triggered when RAG_MIN_SCORE > 0.0 in configuration.

    evidence_available
        At least one usable, above-threshold chunk was found.
        Gemini was called with the bounded evidence.
    """

    NO_EVIDENCE = "no_evidence"
    WEAK_EVIDENCE = "weak_evidence"
    EVIDENCE_AVAILABLE = "evidence_available"


class ConversationTurn(BaseModel):
    """
    A single user or assistant turn in the session conversation history.

    Used to provide bounded context for follow-up question interpretation.
    History is contextual aid ONLY — previous assistant messages are NOT
    authoritative professional evidence. Profile facts must always come from
    retrieved documents.

    role must be "user" or "assistant".
    content is limited to 4000 chars to prevent prompt-stuffing.
    """

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class AskRequest(BaseModel):
    """Request body for POST /profiles/{profile_id}/ask."""

    question: str = Field(..., min_length=1)

    # Optional bounded session history for follow-up question context (Layer 3.6).
    # Hard cap of 50 is enforced here; rag_service applies the configurable
    # MAX_CONVERSATION_MESSAGES limit on top of this.
    # Omit or send [] for a stateless single-turn query.
    conversation_history: list[ConversationTurn] = Field(
        default_factory=list,
        max_length=50,
    )


class SourceReference(BaseModel):
    """
    Provenance for a single piece of retrieved evidence used in the answer.

    These fields let callers trace exactly which document, page, and chunk
    contributed to the response.

    score is the Qdrant cosine similarity and is informational only.
    It MUST NOT be interpreted as a confidence score for factual claims.
    A high score means "this chunk was semantically similar to the query",
    not "this claim is true."
    """

    document_id: uuid.UUID
    filename: str
    page_number: int
    chunk_index: int
    score: Optional[float] = None
    # Private responses only: a short quote from the chunk that was passed to
    # generation. Public responses never carry document text.
    excerpt: Optional[str] = None


class TurnSummary(BaseModel):
    """
    Deterministic digest of one completed turn, for the conversation-summary UI.

    Grounded by construction (see conversation_summary_service). Display only:
    never persisted, never fed back into retrieval or generation.

    outcome:
        answered        grounded answer from profile/document evidence
        not_in_profile  the Rep said it does not have enough information
        contact         contact / handoff turn
        declined        unsupported request
    """

    question: str
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    outcome: Literal["answered", "not_in_profile", "contact", "declined"]


class AskResponse(BaseModel):
    """
    Full RAG response returned by POST /profiles/{profile_id}/ask.

    answer is the Gemini-generated text grounded in the retrieved evidence,
    or the standard "insufficient information" message when evidence is absent
    or weak.

    sources contains provenance for each evidence chunk that was actually
    passed to Gemini.  An empty sources list combined with evidence_status
    of "no_evidence" or "weak_evidence" means Gemini was not called.

    evidence_status distinguishes the retrieval outcome and should be used
    by API consumers to determine the reason for an empty or qualified answer.
    """

    question: str
    answer: str
    sources: list[SourceReference]
    evidence_status: EvidenceStatus
    # Layer 5 — optional orchestration metadata. Existing clients can ignore these.
    intent: Optional[str] = None
    contact_status: Optional[str] = None
    # Conversation-summary digest for this turn. Existing clients can ignore it.
    summary: Optional[TurnSummary] = None
