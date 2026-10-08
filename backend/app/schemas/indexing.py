import uuid

from pydantic import BaseModel


class DocumentIndexResponse(BaseModel):
    """
    Returned by POST /api/v1/documents/{document_id}/index.

    Reports how many chunks were upserted into Qdrant for the document.
    The actual embedding vectors are intentionally NOT returned — they are
    large and not useful in an API response.

    `collection` confirms which Qdrant collection was targeted, making
    the response self-describing in multi-collection environments.

    `profile_id` is taken from the MySQL Document record, never from the
    client, confirming that ownership was enforced server-side.
    """

    document_id: uuid.UUID
    profile_id: uuid.UUID
    indexed_chunks: int
    collection: str
