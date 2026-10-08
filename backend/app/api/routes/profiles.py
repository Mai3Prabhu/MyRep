import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.knowledge import DocumentStatusItem, KnowledgeStatus
from app.schemas.profile import ProfileCreate, ProfileResponse, ProfileUpdate
from app.schemas.rag import AskRequest, AskResponse
from app.schemas.retrieval import SearchRequest, SearchResponse
from app.services import document_service, profile_service, agent_service, search_service

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("/", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: ProfileCreate,
    db: Session = Depends(get_db),
) -> ProfileResponse:
    """Create a new profile."""
    return profile_service.create_profile(db, payload)


@router.get("/lookup", response_model=ProfileResponse)
def lookup_profile(
    name: str,
    db: Session = Depends(get_db),
) -> ProfileResponse:
    """Find an existing profile by name. Returns 404 when none matches."""
    return profile_service.get_profile_by_name(db, name)


@router.get("/{profile_id}", response_model=ProfileResponse)
def get_profile(
    profile_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ProfileResponse:
    """Retrieve a profile by its UUID."""
    return profile_service.get_profile(db, profile_id)


@router.put("/{profile_id}", response_model=ProfileResponse)
def update_profile(
    profile_id: uuid.UUID,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
) -> ProfileResponse:
    """Update an existing profile. Only fields present in the request body are changed."""
    return profile_service.update_profile(db, profile_id, payload)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    """Delete a profile by its UUID."""
    profile_service.delete_profile(db, profile_id)


@router.post(
    "/{profile_id}/search",
    response_model=SearchResponse,
    tags=["retrieval"],
)
def search_profile(
    profile_id: uuid.UUID,
    payload: SearchRequest,
    db: Session = Depends(get_db),
) -> SearchResponse:
    """
    Perform a semantic search over a profile's indexed documents.

    Embeds the query using Gemini Embedding 2 (query task format) and retrieves
    the most semantically similar chunks from Qdrant, filtered strictly to the
    requested profile. Cross-profile retrieval is never performed.

    Request body:
      - query (str): natural-language search question
      - top_k (int, optional): number of results, defaults to RETRIEVAL_TOP_K

    Results are ordered by descending cosine similarity score. An empty list
    means no indexed chunks matched the query for this profile.

    This endpoint returns raw retrieved evidence — it does NOT generate answers.
    LLM generation belongs to a future RAG layer.

    Requires GEMINI_API_KEY and QDRANT_URL to be configured.
    """
    return search_service.search_profile(
        db=db,
        profile_id=profile_id,
        query=payload.query,
        top_k=payload.top_k,
    )


@router.post(
    "/{profile_id}/ask",
    response_model=AskResponse,
    tags=["rag"],
)
def ask_profile(
    profile_id: uuid.UUID,
    payload: AskRequest,
    db: Session = Depends(get_db),
) -> AskResponse:
    """
    Answer a question about a profile using Retrieval-Augmented Generation (RAG).

    Pipeline:
      1. Validates the profile exists in MySQL.
      2. Embeds the question with Gemini Embedding 2 (query format).
      3. Retrieves the most relevant chunks from Qdrant (profile-isolated).
      4. If no evidence is found, returns an "insufficient information" response
         without calling Gemini — the LLM is never invoked on empty context.
      5. Passes retrieved evidence to Gemini to generate a grounded answer.
      6. Returns the answer with full source provenance.

    The generated answer is grounded in the profile's uploaded documents only.
    Gemini is instructed not to invent or assume any professional claims.
    The answer may explicitly acknowledge missing information if the evidence
    is incomplete.

    profile_id is taken from the URL path (MySQL-validated). It is never
    derived from the request body — cross-profile leakage is not possible.

    Requires GEMINI_API_KEY and QDRANT_URL to be configured.
    """
    return agent_service.handle_question(
        db=db,
        profile_id=profile_id,
        question=payload.question,
        conversation_history=payload.conversation_history or None,
    )


@router.get(
    "/{profile_id}/knowledge-status",
    response_model=KnowledgeStatus,
    tags=["knowledge"],
)
def get_knowledge_status(
    profile_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> KnowledgeStatus:
    """
    Return aggregated indexing readiness for all documents in a profile.

    rag_ready is True when at least one document is in INDEXED state, meaning
    the /ask endpoint can return answers grounded in real evidence.

    Use this endpoint to display the Knowledge Base readiness banner on the
    frontend profile page.
    """
    return document_service.get_knowledge_status(db, profile_id)


@router.get(
    "/{profile_id}/documents/status",
    response_model=list[DocumentStatusItem],
    tags=["knowledge"],
)
def get_documents_status(
    profile_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[DocumentStatusItem]:
    """
    Return per-document indexing status for all documents in a profile.

    Each item includes the document's indexing_status
    (NOT_INDEXED / INDEXING / INDEXED / FAILED), the indexed_at timestamp,
    the indexed_chunks count, and a sanitised indexing_error message when
    status is FAILED.

    Use this endpoint to populate the document status list on the frontend
    Knowledge Base section.
    """
    return document_service.get_documents_status(db, profile_id)
