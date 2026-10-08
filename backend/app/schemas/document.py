import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    """
    What the API returns for a document.

    storage_path is intentionally excluded — it is an internal implementation
    detail that callers should never depend on. Future layers will expose
    a signed download URL instead.

    indexing_error is excluded from this response — it is exposed only via
    the dedicated /documents/status endpoint (DocumentStatusItem).
    """

    id: uuid.UUID
    profile_id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    indexing_status: str = "NOT_INDEXED"
    indexed_at: Optional[datetime] = None
    indexed_chunks: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
