import uuid

from pydantic import BaseModel, Field

from app.core.config import settings


class SearchRequest(BaseModel):
    """
    Request body for POST /api/v1/profiles/{profile_id}/search.

    `top_k` defaults to the configured RETRIEVAL_TOP_K but can be
    overridden per-request within a reasonable range.
    """

    query: str
    top_k: int = Field(default_factory=lambda: settings.RETRIEVAL_TOP_K, ge=1, le=50)


class RetrievedChunk(BaseModel):
    """
    One result returned by a semantic search.

    Provenance fields let the caller know exactly where this text came from:
    which document, which page, and which chunk within that page.

    `score` is the cosine similarity returned by Qdrant (higher = more similar).
    It is a retrieval signal, not a measure of correctness.

    The text is the raw chunk as it was indexed, with no LLM post-processing.
    Generation and answer synthesis belong to a later RAG layer.
    """

    document_id: uuid.UUID
    filename: str
    page_number: int
    chunk_index: int
    text: str
    score: float


class SearchResponse(BaseModel):
    """
    Full response for POST /api/v1/profiles/{profile_id}/search.

    `results` is ordered by descending relevance score.
    An empty list means no indexed chunks matched the query within the
    configured similarity threshold (or no documents have been indexed
    for this profile yet).
    """

    query: str
    profile_id: uuid.UUID
    results: list[RetrievedChunk]
