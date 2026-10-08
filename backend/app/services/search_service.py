"""
search_service.py — Semantic search orchestration for Layer 2.6.

This service owns the query retrieval pipeline:

    user query (string)
        ↓
    embed_query()       — Gemini Embedding 2 with query task prefix
        ↓
    qdrant_service.search_chunks()   — cosine similarity + profile_id filter
        ↓
    list[RetrievedChunk]

It is the only service that connects the embedding layer to the Qdrant search
layer. It knows about MySQL (to validate the profile), Gemini (for query
embeddings via embedding_service), and Qdrant (via qdrant_service), but it
does NOT generate answers — that belongs to a future RAG layer.

Profile isolation guarantee
---------------------------
The profile_id passed to Qdrant must come from a validated MySQL profile, not
from arbitrary client input. The route validates the profile exists before
calling this service, but this service also receives the profile_id from the
route and passes it directly to qdrant_service — never from the query body.

Retrieval is NOT generation
---------------------------
This service returns raw chunk text with similarity scores. It does NOT:
  - call a language model
  - summarise or synthesise results
  - make claims about the profile owner
  - filter results by a relevance threshold

Those decisions belong to the RAG layer (Layer 2.7+).
"""

import uuid

from sqlalchemy.orm import Session

from app.core import voice_timing
from app.schemas.retrieval import SearchResponse
from app.services import embedding_service, profile_service, qdrant_service


def search_profile(
    db: Session,
    profile_id: uuid.UUID,
    query: str,
    top_k: int,
) -> SearchResponse:
    """
    Embed a query and retrieve the top-k most relevant chunks for a profile.

    Steps:
    1. Confirm the profile exists in MySQL (raises 404 if not found).
    2. Embed the query text using the query task format via Gemini Embedding 2.
    3. Search Qdrant with a mandatory profile_id payload filter.
    4. Return ranked results with full provenance (document, page, chunk).

    Args:
        db:         SQLAlchemy session for MySQL profile validation.
        profile_id: Target profile — only chunks for this profile are returned.
        query:      Natural-language search query from the user.
        top_k:      Maximum number of results to return.

    Returns:
        SearchResponse with ranked RetrievedChunk list.

    Raises:
        HTTPException(404): Profile does not exist.
        HTTPException(400): Query is empty.
        HTTPException(503): Gemini or Qdrant is not configured.
        HTTPException(502): Gemini or Qdrant API call failed.
    """
    # Validate profile ownership — raises 404 if the profile doesn't exist.
    profile_service.get_profile(db, profile_id)

    voice_timing.mark("embedding_start")
    query_vector = embedding_service.embed_query(query)
    voice_timing.mark("embedding_end")

    voice_timing.mark("vector_search_start")
    results = qdrant_service.search_chunks(
        profile_id=profile_id,
        query_vector=query_vector,
        top_k=top_k,
    )
    voice_timing.mark("vector_search_end")

    return SearchResponse(
        query=query,
        profile_id=profile_id,
        results=results,
    )
