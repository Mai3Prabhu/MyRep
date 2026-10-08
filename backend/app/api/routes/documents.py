import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.document import DocumentResponse
from app.schemas.extraction import DocumentExtractionResponse
from app.schemas.chunking import DocumentChunkingResponse
from app.schemas.embedding import DocumentEmbeddingResponse
from app.schemas.indexing import DocumentIndexResponse
from app.services import document_service

# Routes nested under a profile: /profiles/{profile_id}/documents
profile_documents_router = APIRouter(prefix="/profiles", tags=["documents"])

# Standalone document route: /documents/{document_id}
documents_router = APIRouter(prefix="/documents", tags=["documents"])


@profile_documents_router.post(
    "/{profile_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    profile_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """
    Upload a PDF document for a profile.

    Accepts multipart/form-data with a 'file' field containing a PDF.
    Returns document metadata — not the file content.
    """
    return await document_service.upload_document(db, profile_id, file)


@profile_documents_router.get(
    "/{profile_id}/documents",
    response_model=list[DocumentResponse],
)
def list_documents(
    profile_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[DocumentResponse]:
    """Return all documents belonging to a profile."""
    return document_service.list_documents(db, profile_id)


@documents_router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Retrieve metadata for a single document by its UUID."""
    return document_service.get_document(db, document_id)


@documents_router.post(
    "/{document_id}/extract",
    response_model=DocumentExtractionResponse,
    tags=["extraction"],
)
def extract_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DocumentExtractionResponse:
    """
    Extract text from a stored PDF document, page-by-page.

    The document_id is used to locate the trusted storage path from MySQL.
    No filesystem path is ever accepted from the client.

    Returns structured page-level text with provenance (document_id, filename,
    page_number per page). Image-only pages are returned with has_text=false
    and an empty text field — no OCR or fabricated text is produced.

    This endpoint is a development/processing tool for Layer 2.2.
    Extracted text is not persisted — that belongs to Layer 2.3.
    """
    return document_service.extract_document(db, document_id)


@documents_router.post(
    "/{document_id}/chunks",
    response_model=DocumentChunkingResponse,
    tags=["chunking"],
)
def chunk_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DocumentChunkingResponse:
    """
    Extract and chunk a stored PDF document into bounded, page-scoped segments.

    Flow: document_id → MySQL record → trusted storage path → pypdf extraction
    → paragraph-aware chunking → structured chunk list.

    Each chunk carries full provenance: document_id, filename, page_number,
    chunk_index. This output is ready for Gemini embedding in Layer 2.4.

    Nothing is persisted — chunking is a runtime transformation.
    """
    return document_service.chunk_document(db, document_id)


@documents_router.post(
    "/{document_id}/embeddings",
    response_model=DocumentEmbeddingResponse,
    tags=["embeddings"],
)
def embed_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DocumentEmbeddingResponse:
    """
    Extract, chunk, and embed a stored PDF document via Gemini Embedding 2.

    Flow: document_id → MySQL record → trusted storage path → pypdf extraction
    → paragraph-aware chunking → Gemini Embedding 2 API → embedding vectors.

    Document chunks are embedded using the asymmetric retrieval document format:

        title: {filename} | text: {chunk_text}

    Vectors are NOT persisted — Layer 2.5 (Qdrant) will store them.
    This endpoint is a development/testing pipeline step for Layer 2.4.

    Requires GEMINI_API_KEY to be configured in the backend environment.
    The API key is never included in responses or error messages.
    """
    return document_service.embed_document(db, document_id)


@documents_router.post(
    "/{document_id}/index",
    response_model=DocumentIndexResponse,
    tags=["indexing"],
)
def index_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DocumentIndexResponse:
    """
    Run the full pipeline — extract, chunk, embed — and persist vectors in Qdrant.

    Flow: document_id → MySQL record → profile_id (trusted, from DB) →
    pypdf extraction → paragraph-aware chunking → Gemini Embedding 2 (batch) →
    Qdrant upsert (stale points removed first).

    The document's profile_id is always taken from MySQL — it is never
    supplied by the client.

    Re-indexing the same document is safe: stale Qdrant points are deleted
    before the new set is upserted, so there are no duplicate or orphan points.

    Requires both GEMINI_API_KEY and QDRANT_URL to be configured.
    """
    return document_service.index_document(db, document_id)
