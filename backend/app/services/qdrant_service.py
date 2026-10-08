"""
qdrant_service.py — Qdrant Cloud operations for MyRep.

Responsibilities (and ONLY these):
  - Qdrant client construction
  - Collection creation / validation
  - Upserting embedded document chunks as Qdrant points
  - Removing stale points when a document is re-indexed
  - Semantic search with mandatory profile_id payload filter

This service knows nothing about MySQL, PDF files, chunking, or Gemini.
It receives already-embedded chunks and works entirely within Qdrant.

Collection design
-----------------
One shared collection — `myrep_knowledge` — stores chunks from ALL profiles.
Profile isolation is enforced through a payload filter on `profile_id`, NOT
by separate per-profile collections. This means:

  - A single Qdrant collection is easy to manage and monitor.
  - Adding a new profile requires no schema changes in Qdrant.
  - Every search MUST supply a profile_id filter. This is not optional.

Point payload
-------------
Each point stores:
  - profile_id   — mandatory for retrieval isolation
  - document_id  — for provenance and stale-point cleanup
  - filename     — human-readable document name
  - page_number  — source page within the document
  - chunk_index  — position within the document chunk sequence
  - text         — the raw chunk text (returned with search results)

profile_id and document_id are stored as strings because Qdrant payload
filters use string equality matching.

Deterministic point IDs
-----------------------
Each point's ID is derived from (document_id, chunk_index) using UUID v5:

    uuid.uuid5(MYREP_NS, f"{document_id}:{chunk_index}")

This means:
  - Re-indexing the same chunk overwrites the old point (upsert semantics).
  - No random IDs are generated, so idempotency is guaranteed.
  - Qdrant accepts UUID strings as point IDs natively.

Re-indexing strategy
--------------------
When a document is re-indexed:
  1. All existing points for the document are deleted by payload filter.
  2. The new set of points is upserted.

This handles the case where a document is reprocessed and produces fewer
chunks than before (which would leave orphan points if we only upserted).
The delete + upsert sequence is not atomic, but for an MVP this is
acceptable — the window of inconsistency is small.

Collection initialization
-------------------------
`ensure_collection()` is called once at app startup (via lifespan in
main.py). It checks whether the collection exists and creates it only if
absent. Subsequent calls on an already-running server are safe (no-op).
"""

import uuid

from fastapi import HTTPException, status
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Range,
    VectorParams,
)

from app.core.config import settings
from app.schemas.embedding import EmbeddedChunk
from app.schemas.retrieval import RetrievedChunk


# ---------------------------------------------------------------------------
# Namespace UUID for deterministic point ID generation (UUID v5).
# This value is fixed and must never change — changing it would invalidate
# all existing point IDs and require a full re-index.
# ---------------------------------------------------------------------------
_MYREP_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # UUID NS_URL


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_config() -> tuple[str, str]:
    """
    Return (QDRANT_URL, QDRANT_API_KEY) from settings.

    Raises HTTP 503 if QDRANT_URL is absent. The API key may be empty for
    local Qdrant deployments (no auth required), so only the URL is checked.
    """
    url = settings.QDRANT_URL
    if not url or not url.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "QDRANT_URL is not configured. "
                "Set it in the backend .env file and restart the server."
            ),
        )
    return url, settings.QDRANT_API_KEY


def _make_client() -> QdrantClient:
    """
    Construct a QdrantClient from configuration.

    Uses HTTPS by default (Qdrant Cloud). For local Qdrant without TLS,
    set QDRANT_URL to http://localhost:6333.

    The API key is passed only when it is non-empty — local Qdrant
    instances typically run without authentication.
    """
    url, api_key = _require_config()
    return QdrantClient(
        url=url,
        api_key=api_key if api_key and api_key.strip() else None,
    )


def point_id_for(document_id: uuid.UUID, chunk_index: int) -> str:
    """
    Return a deterministic UUID string for a (document_id, chunk_index) pair.

    UUID v5 hashes the namespace UUID and the name string, so the same inputs
    always produce the same output. Qdrant accepts UUID strings as point IDs.
    """
    name = f"{document_id}:{chunk_index}"
    return str(uuid.uuid5(_MYREP_NS, name))


def _chunk_to_point(profile_id: uuid.UUID, chunk: EmbeddedChunk) -> PointStruct:
    """
    Convert an EmbeddedChunk into a Qdrant PointStruct.

    The payload carries all provenance metadata needed for retrieval results
    and for identifying stale points on re-indexing.
    """
    return PointStruct(
        id=point_id_for(chunk.document_id, chunk.chunk_index),
        vector=chunk.embedding,
        payload={
            "profile_id": str(profile_id),
            "document_id": str(chunk.document_id),
            "filename": chunk.filename,
            "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
        },
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ensure_collection() -> None:
    """
    Create the Qdrant collection if it does not already exist.

    Called once at app startup. Safe to call multiple times — it checks
    for existence before attempting creation.

    If QDRANT_URL is not configured, the call is silently skipped so the
    application can start without Qdrant (e.g. for running unit tests).

    Raises:
        HTTPException(503): QDRANT_URL is configured but the collection
                            cannot be created (connection failure, auth error).
    """
    if not settings.QDRANT_URL or not settings.QDRANT_URL.strip():
        # Qdrant not configured — skip silently (e.g. during unit tests).
        return

    try:
        client = _make_client()
        if not client.collection_exists(settings.QDRANT_COLLECTION):
            client.create_collection(
                collection_name=settings.QDRANT_COLLECTION,
                vectors_config=VectorParams(
                    size=settings.EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
        # Filtered delete and search require payload indexes on Qdrant Cloud.
        for field_name, field_schema in (
            ("profile_id", PayloadSchemaType.KEYWORD),
            ("document_id", PayloadSchemaType.KEYWORD),
            ("chunk_index", PayloadSchemaType.INTEGER),
        ):
            client.create_payload_index(
                collection_name=settings.QDRANT_COLLECTION,
                field_name=field_name,
                field_schema=field_schema,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Failed to initialize Qdrant collection "
                f"'{settings.QDRANT_COLLECTION}': "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc


def index_embedded_chunks(
    profile_id: uuid.UUID,
    document_id: uuid.UUID,
    embedded_chunks: list[EmbeddedChunk],
) -> int:
    """
    Persist embedded chunks into Qdrant, replacing any previous version.

    Steps:
    1. Delete all existing points whose payload.document_id matches
       the document being indexed. This handles re-indexing and the case
       where a reprocessed document produces fewer chunks than before.
    2. Upsert the new set of points.

    The delete + upsert is not atomic, but the inconsistency window is
    acceptably small for an MVP.

    Args:
        profile_id:       From MySQL — never supplied by the client.
        document_id:      UUID of the document being indexed.
        embedded_chunks:  Output of embedding_service.embed_chunks().

    Returns:
        Number of points upserted.

    Raises:
        HTTPException(400): No chunks to index.
        HTTPException(502): Qdrant operation failed.
        HTTPException(503): Qdrant not configured.
    """
    if not embedded_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No embedded chunks provided for indexing.",
        )

    client = _make_client()
    collection = settings.QDRANT_COLLECTION
    new_chunk_count = len(embedded_chunks)

    # Step 1: Upsert the new points first.
    #
    # Deterministic point IDs (uuid5) mean re-uploading an existing chunk
    # simply overwrites it in-place — this is idempotent and safe.
    # If this step fails, the previous index for this document is still intact.
    points = [_chunk_to_point(profile_id, chunk) for chunk in embedded_chunks]

    try:
        client.upsert(
            collection_name=collection,
            points=points,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Failed to upsert {len(points)} points into Qdrant "
                f"collection '{collection}': "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc

    # Step 2: Delete only stale points — those with chunk_index >= new_chunk_count.
    #
    # A re-chunked document may produce fewer chunks than before (e.g. after
    # content removal). The points for old chunk indices beyond the new total
    # are now orphaned and must be purged.
    #
    # This runs AFTER a successful upsert so the document is never momentarily
    # unindexed. If this delete fails, the extra old-index points are harmless:
    # they carry a lower relevance rank than the freshly upserted chunks and
    # will be cleaned up on the next successful re-index.
    try:
        client.delete(
            collection_name=collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=str(document_id)),
                        ),
                        FieldCondition(
                            key="chunk_index",
                            range=Range(gte=new_chunk_count),
                        ),
                    ]
                )
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Failed to remove stale Qdrant points for document {document_id}: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc

    return len(points)


def search_chunks(
    profile_id: uuid.UUID,
    query_vector: list[float],
    top_k: int,
) -> list[RetrievedChunk]:
    """
    Perform a cosine similarity search in Qdrant, filtered to one profile.

    The profile_id filter is MANDATORY and is applied as a Qdrant server-side
    filter — not post-hoc in Python. This enforces profile isolation at the
    retrieval layer, not at the application layer.

    Args:
        profile_id:    Only chunks belonging to this profile are returned.
        query_vector:  Embedded query (from embedding_service.embed_query).
        top_k:         Maximum number of results to return.

    Returns:
        Ranked list of RetrievedChunk, ordered by descending similarity score.

    Raises:
        HTTPException(502): Qdrant search failed.
        HTTPException(503): Qdrant not configured.
    """
    client = _make_client()

    profile_filter = Filter(
        must=[
            FieldCondition(
                key="profile_id",
                match=MatchValue(value=str(profile_id)),
            )
        ]
    )

    try:
        query_response = client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=query_vector,
            query_filter=profile_filter,
            limit=top_k,
            with_payload=True,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Qdrant search failed: {type(exc).__name__}: {exc}"
            ),
        ) from exc

    results: list[RetrievedChunk] = []
    for sp in query_response.points:
        payload = sp.payload or {}
        results.append(
            RetrievedChunk(
                document_id=uuid.UUID(payload["document_id"]),
                filename=payload["filename"],
                page_number=payload["page_number"],
                chunk_index=payload["chunk_index"],
                text=payload["text"],
                score=sp.score,
            )
        )

    return results
