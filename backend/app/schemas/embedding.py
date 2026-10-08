import uuid

from pydantic import BaseModel


class EmbeddedChunk(BaseModel):
    """
    A DocumentChunk paired with its Gemini embedding vector.

    Provenance fields mirror DocumentChunk exactly so callers can map
    each vector back to its source without a separate database lookup.

    The `embedding` field is the raw float vector returned by Gemini.
    It is NOT persisted here — Layer 2.5 (Qdrant) is responsible for
    storing and indexing vectors.

    `embedding_dimension` records the actual length of the returned
    vector, making validation failures visible in API responses during
    development/testing.
    """

    document_id: uuid.UUID
    filename: str
    page_number: int
    chunk_index: int
    embedding_dimension: int
    embedding: list[float]
    text: str


class DocumentEmbeddingResponse(BaseModel):
    """
    Full embedding result for one document.

    Returned by POST /api/v1/documents/{document_id}/embeddings.
    This endpoint is a development/testing pipeline step — vectors are
    NOT persisted. Layer 2.5 will store them in Qdrant.

    `embedding_dimension` records the dimensionality used for this run,
    so callers can verify alignment with their Qdrant collection config.
    """

    document_id: uuid.UUID
    filename: str
    chunk_count: int
    embedding_dimension: int
    chunks: list[EmbeddedChunk]
