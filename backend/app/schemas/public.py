"""
Public-facing schemas for Layers 4 / 4.1.

These are a deliberate security boundary. They are NOT aliases of the
private ProfileResponse / AskResponse models. Internal fields such as
contact_preferences, timestamps, document IDs, storage paths, Qdrant
IDs, and indexing metadata must never appear here.
"""

from typing import Any

from pydantic import BaseModel

from app.schemas.rag import EvidenceStatus, TurnSummary


class PublicProfile(BaseModel):
    """
    Professional identity visible to recruiters and other public visitors.

    id is included so the public chat URL can be constructed without a
    second lookup. It is a share identifier, not an invitation to call
    private management endpoints.

    knowledge_ready is a boolean only — it does not expose document counts,
    indexing errors, or internal status values.
    """

    id: str
    name: str
    headline: str | None = None
    about: str | None = None
    skills: list[Any] | None = None
    experience: list[Any] | None = None
    projects: list[Any] | None = None
    education: list[Any] | None = None
    knowledge_ready: bool = False

    model_config = {"extra": "forbid"}


class PublicSourceReference(BaseModel):
    """
    Safe provenance for a public answer.

    filename is the original upload name with any path components stripped.
    page_number is the PDF page the chunk came from.

    Intentionally omitted: document_id, chunk_index, score, storage_path.
    """

    filename: str
    page_number: int

    model_config = {"extra": "forbid"}


class PublicAskResponse(BaseModel):
    """Grounded RAG answer returned by the public /ask endpoint."""

    question: str
    answer: str
    sources: list[PublicSourceReference]
    evidence_status: EvidenceStatus
    intent: str | None = None
    contact_status: str | None = None
    # Built only from the visitor's question, the Rep's answer, and names in
    # public profile fields. Contains no document text.
    summary: TurnSummary | None = None

    model_config = {"extra": "forbid"}
