import uuid

from pydantic import BaseModel


class DocumentChunk(BaseModel):
    """
    A bounded text segment produced from a single page of a document.

    Provenance fields:
    - document_id: the source document
    - filename: human-readable document name (for display/debugging)
    - page_number: 1-indexed page the text was extracted from
    - chunk_index: 0-indexed position within the full document (across all
      pages). Monotonically increasing and deterministic — same document always
      produces the same indices in the same order.

    The tuple (document_id, chunk_index) uniquely identifies a chunk.

    This schema is designed so it can be used directly as a Qdrant point
    payload in Layer 2.4, alongside a vector generated from `text`:

        {
            "document_id": "...",
            "filename": "resume.pdf",
            "page_number": 2,
            "chunk_index": 4,
            "text": "..."
        }
    """

    document_id: uuid.UUID
    filename: str
    page_number: int
    chunk_index: int
    text: str


class DocumentChunkingResponse(BaseModel):
    """
    Full chunking result for one document.

    chunk_size and chunk_overlap record the configuration used for this run,
    so callers can understand the chunk boundaries without inspecting config.
    """

    document_id: uuid.UUID
    filename: str
    chunk_count: int
    chunk_size: int
    chunk_overlap: int
    chunks: list[DocumentChunk]
