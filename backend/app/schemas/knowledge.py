import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class IndexingStatus(str, Enum):
    NOT_INDEXED = "NOT_INDEXED"
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class DocumentStatusItem(BaseModel):
    """
    Per-document indexing status returned by
    GET /api/v1/profiles/{profile_id}/documents/status.

    indexing_error is a sanitised user-facing message (no filesystem paths or
    internal exception details). Full error details are in the server log.
    """

    id: uuid.UUID
    filename: str
    indexing_status: IndexingStatus
    indexed_at: Optional[datetime] = None
    indexed_chunks: Optional[int] = None
    indexing_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeStatus(BaseModel):
    """
    Aggregated knowledge readiness for a profile, returned by
    GET /api/v1/profiles/{profile_id}/knowledge-status.

    rag_ready is True when at least one document is INDEXED — meaning the
    /ask endpoint can return grounded answers from real evidence.
    """

    profile_id: uuid.UUID
    total_documents: int
    indexed_documents: int
    not_indexed_documents: int
    failed_documents: int
    rag_ready: bool
