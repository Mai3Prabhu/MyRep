import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Document
from app.schemas.document import DocumentResponse
from app.schemas.extraction import DocumentExtractionResponse
from app.schemas.chunking import DocumentChunkingResponse
from app.schemas.embedding import DocumentEmbeddingResponse
from app.schemas.indexing import DocumentIndexResponse
from app.schemas.knowledge import DocumentStatusItem, IndexingStatus, KnowledgeStatus
from app.services import (
    profile_service,
    storage_service,
    pdf_extraction_service,
    chunking_service,
    embedding_service,
    qdrant_service,
)

logger = logging.getLogger(__name__)

# The PDF magic bytes that every valid PDF file must start with.
_PDF_MAGIC = b"%PDF"

# MIME types we accept from the client's Content-Type header.
_ACCEPTED_CONTENT_TYPES = {"application/pdf"}


def _validate_file(filename: str | None, content_type: str | None, content: bytes) -> None:
    """
    Raise an appropriate HTTPException if the uploaded file is not a valid PDF
    within the configured size limit.

    Two independent checks are applied:
    1. Magic bytes — reliable, cannot be spoofed by the client.
    2. Content-Type header — best-effort, used as an early signal.
    """
    max_bytes = settings.MAX_DOCUMENT_SIZE_MB * 1024 * 1024

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.MAX_DOCUMENT_SIZE_MB} MB limit.",
        )

    if not content.startswith(_PDF_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are accepted. The uploaded file does not appear to be a PDF.",
        )

    if content_type and content_type not in _ACCEPTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type '{content_type}'. Upload a PDF file.",
        )


async def upload_document(
    db: Session,
    profile_id: uuid.UUID,
    file: UploadFile,
) -> Document:
    """
    Validate the upload, persist the file to disk, and create a Document row.

    Steps:
    1. Confirm the profile exists (raises 404 if not).
    2. Read all file bytes into memory.
    3. Validate size and PDF magic bytes.
    4. Write the file to local storage via storage_service.
    5. Insert a Document record in MySQL.
    6. Return the ORM object.
    """
    profile_service.get_profile(db, profile_id)

    content = await file.read()

    _validate_file(file.filename, file.content_type, content)

    original_name = file.filename or "upload.pdf"

    try:
        storage_path = storage_service.save_file(profile_id, original_name, content)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save the uploaded file. Please try again.",
        ) from exc

    document = Document(
        profile_id=profile_id,
        filename=original_name,
        content_type=file.content_type or "application/pdf",
        file_size=len(content),
        storage_path=storage_path,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def list_documents(db: Session, profile_id: uuid.UUID) -> list[Document]:
    """
    Return all documents belonging to a profile.
    Raises 404 if the profile does not exist.
    """
    profile_service.get_profile(db, profile_id)
    return db.query(Document).filter(Document.profile_id == profile_id).all()


def get_document(db: Session, document_id: uuid.UUID) -> Document:
    """
    Fetch a single document by its UUID. Raises 404 if not found.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found.",
        )
    return document


def extract_document(
    db: Session, document_id: uuid.UUID
) -> DocumentExtractionResponse:
    """
    Locate the stored PDF for a document and extract text page-by-page.

    Flow:
    1. Fetch the Document record from MySQL (raises 404 if not found).
    2. Resolve the storage_path to a filesystem Path via storage_service.
       The path comes from the trusted database record, never from the client.
    3. Pass the Path to pdf_extraction_service.extract_pages().
    4. Return structured page-level text with provenance (document_id, filename,
       page_number per page). Image-only pages are returned with has_text=false
       and an empty text field — no OCR or fabricated text is produced.

    This endpoint is a development/processing tool for Layer 2.2.
    Extracted text is not persisted — that belongs to Layer 2.3.
    """
    document = get_document(db, document_id)
    pdf_path = storage_service.get_file_path(document.storage_path)
    pages = pdf_extraction_service.extract_pages(pdf_path)

    return DocumentExtractionResponse(
        document_id=document.id,
        filename=document.filename,
        page_count=len(pages),
        pages=pages,
    )


def chunk_document(
    db: Session, document_id: uuid.UUID
) -> DocumentChunkingResponse:
    """
    Extract and chunk a stored PDF document.

    Flow:
    1. Fetch Document record from MySQL.
    2. Resolve storage_path to a Path via storage_service (trusted DB source).
    3. Extract pages using pdf_extraction_service.
    4. Chunk the extracted pages using chunking_service.
    5. Return the full chunking result with provenance.

    Nothing is persisted — chunking is a runtime transformation.
    Layer 2.4 will decide what to embed and store in Qdrant.
    """
    document = get_document(db, document_id)
    pdf_path = storage_service.get_file_path(document.storage_path)
    pages = pdf_extraction_service.extract_pages(pdf_path)
    chunks = chunking_service.chunk_pages(
        document_id=document.id,
        filename=document.filename,
        pages=pages,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )
    return DocumentChunkingResponse(
        document_id=document.id,
        filename=document.filename,
        chunk_count=len(chunks),
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        chunks=chunks,
    )


def embed_document(
    db: Session, document_id: uuid.UUID
) -> DocumentEmbeddingResponse:
    """
    Extract, chunk, and embed a stored PDF document via Gemini Embedding 2.

    Flow:
    1. Fetch Document record from MySQL.
    2. Resolve storage_path to a Path via storage_service (trusted DB source).
    3. Extract pages using pdf_extraction_service.
    4. Chunk the extracted pages using chunking_service.
    5. Embed all chunks in a single Gemini API call via embedding_service.
    6. Return the full embedding result.

    Nothing is persisted — Layer 2.5 (Qdrant) will store the vectors.
    This endpoint is a development/testing pipeline step.
    """
    document = get_document(db, document_id)
    pdf_path = storage_service.get_file_path(document.storage_path)
    pages = pdf_extraction_service.extract_pages(pdf_path)
    chunks = chunking_service.chunk_pages(
        document_id=document.id,
        filename=document.filename,
        pages=pages,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )
    embedded_chunks = embedding_service.embed_chunks(chunks)
    return DocumentEmbeddingResponse(
        document_id=document.id,
        filename=document.filename,
        chunk_count=len(embedded_chunks),
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        chunks=embedded_chunks,
    )


def index_document(
    db: Session, document_id: uuid.UUID
) -> DocumentIndexResponse:
    """
    Run the full indexing pipeline for a document and persist vectors in Qdrant.

    Flow:
    1. Fetch Document record from MySQL — this is the source of profile_id.
       profile_id is NEVER accepted from the client.
    2. Mark the document as INDEXING (persisted immediately so status reflects
       in-progress work during the synchronous request).
    3. Resolve the storage path from the trusted DB record.
    4. Extract pages from the PDF.
    5. Chunk the extracted pages.
    6. Embed all chunks via Gemini Embedding 2 (single batch API call).
    7. Upsert the embedded chunks into the Qdrant `myrep_knowledge` collection,
       stale points removed via the Layer 2.5 upsert-first strategy.
    8. On success: mark INDEXED with timestamp and chunk count.
       On failure: mark FAILED with a sanitised user-facing error message.
    9. Return a summary with the indexed chunk count.

    Re-indexing the same document is safe and idempotent.
    """
    document = get_document(db, document_id)

    # Mark INDEXING before doing any work so status is visible immediately.
    document.indexing_status = IndexingStatus.INDEXING.value
    document.indexing_error = None
    db.commit()

    try:
        pdf_path = storage_service.get_file_path(document.storage_path)
        pages = pdf_extraction_service.extract_pages(pdf_path)
        chunks = chunking_service.chunk_pages(
            document_id=document.id,
            filename=document.filename,
            pages=pages,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )

        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Document {document_id} produced no text chunks. "
                    "The PDF may be image-only or contain no extractable text."
                ),
            )

        embedded_chunks = embedding_service.embed_chunks(chunks)
        indexed_count = qdrant_service.index_embedded_chunks(
            profile_id=document.profile_id,
            document_id=document.id,
            embedded_chunks=embedded_chunks,
        )
    except HTTPException as exc:
        # Keep the empty-PDF case specific. Other failures (embedding, Qdrant)
        # must not be reported as a missing-text problem.
        detail = exc.detail if isinstance(exc.detail, str) else ""
        if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY and "no text chunks" in detail:
            user_error = "No extractable text found in this PDF."
        elif exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
            user_error = detail or "This PDF could not be indexed."
        else:
            user_error = "Indexing failed. Please try again."
        document.indexing_status = IndexingStatus.FAILED.value
        document.indexing_error = user_error
        db.commit()
        raise
    except Exception as exc:
        logger.error(
            "index_document_failed document_id=%s exc_type=%s",
            document_id,
            type(exc).__name__,
        )
        document.indexing_status = IndexingStatus.FAILED.value
        document.indexing_error = "Indexing failed. Please try again."
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Indexing failed due to an internal error. Please try again.",
        ) from exc

    # Success — record the outcome.
    document.indexing_status = IndexingStatus.INDEXED.value
    document.indexed_at = datetime.now(timezone.utc)
    document.indexed_chunks = indexed_count
    document.indexing_error = None
    db.commit()

    return DocumentIndexResponse(
        document_id=document.id,
        profile_id=document.profile_id,
        indexed_chunks=indexed_count,
        collection=settings.QDRANT_COLLECTION,
    )


# ---------------------------------------------------------------------------
# Layer 2.9 — Knowledge status endpoints
# ---------------------------------------------------------------------------


def get_knowledge_status(db: Session, profile_id: uuid.UUID) -> KnowledgeStatus:
    """
    Return aggregated indexing readiness for all documents in a profile.

    rag_ready is True when at least one document is INDEXED, meaning the
    /ask endpoint can return grounded answers.
    """
    profile_service.get_profile(db, profile_id)

    documents = db.query(Document).filter(Document.profile_id == profile_id).all()

    total = len(documents)
    indexed = sum(1 for d in documents if d.indexing_status == IndexingStatus.INDEXED.value)
    failed = sum(1 for d in documents if d.indexing_status == IndexingStatus.FAILED.value)
    not_indexed = sum(
        1 for d in documents
        if d.indexing_status in (IndexingStatus.NOT_INDEXED.value, IndexingStatus.INDEXING.value)
    )

    return KnowledgeStatus(
        profile_id=profile_id,
        total_documents=total,
        indexed_documents=indexed,
        not_indexed_documents=not_indexed,
        failed_documents=failed,
        rag_ready=indexed > 0,
    )


def get_documents_status(db: Session, profile_id: uuid.UUID) -> list[DocumentStatusItem]:
    """
    Return per-document indexing status for all documents in a profile.
    Ordered by created_at ascending (most recently uploaded last).
    """
    profile_service.get_profile(db, profile_id)

    documents = (
        db.query(Document)
        .filter(Document.profile_id == profile_id)
        .order_by(Document.created_at.asc())
        .all()
    )
    return [DocumentStatusItem.model_validate(d) for d in documents]
