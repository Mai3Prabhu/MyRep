"""
embedding_service.py — Gemini Embedding 2 integration.

Pure transformation:

    list[DocumentChunk]  →  list[EmbeddedChunk]

This service knows nothing about MySQL, Qdrant, PDF files, chunking, or
retrieval. Its sole responsibility is converting text into float vectors
via the Gemini Embedding 2 API.

Document embedding format
-------------------------
For asymmetric retrieval, Gemini Embedding 2 recommends encoding document
chunks with a distinguishing prefix. We use:

    title: {filename} | text: {chunk_text}

Metadata fields (document_id, page_number, chunk_index) are intentionally
excluded from the embedded text. They are provenance/payload data that will
live in the Qdrant point payload in Layer 2.5 — not semantic content.

Future query format (Layer 2.6, NOT implemented here):

    task: search result | query: {user_question}

Batching
--------
gemini-embedding-2 accepts one content per request. Passing a list of
strings makes the SDK collapse them into a single content, and the API
then returns one embedding for the whole list. Each chunk is therefore
embedded in its own call, in input order.

Dimension validation
--------------------
After every API call the returned vector length is checked against
EMBEDDING_DIMENSION. A mismatch raises an HTTPException immediately —
Qdrant collection dimensions must match exactly and silent truncation
would corrupt future similarity searches.
"""

from google import genai
from google.genai import types
from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.chunking import DocumentChunk
from app.schemas.embedding import EmbeddedChunk


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_api_key() -> str:
    """
    Return the configured Gemini API key.

    Raises HTTP 503 if the key is absent rather than passing an empty string
    to the SDK (which would produce a confusing authentication error instead of
    a clear configuration message).

    The key is NEVER included in exception messages or log output.
    """
    key = settings.GEMINI_API_KEY
    if not key or not key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "GEMINI_API_KEY is not configured. "
                "Set it in the backend .env file and restart the server."
            ),
        )
    return key


def _make_client() -> genai.Client:
    """Construct a Gemini client from the configured API key."""
    return genai.Client(
        api_key=_require_api_key(),
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def _format_for_embedding(chunk: DocumentChunk) -> str:
    """
    Build the embedding input string for a document chunk.

    Uses the asymmetric retrieval document format recommended by Gemini
    Embedding 2:

        title: {filename} | text: {chunk_text}

    The `filename` acts as the semantic title — it is the only human-readable
    identifier for the document that meaningfully describes its subject.
    Numeric identifiers (document_id, chunk_index, page_number) carry no
    semantic signal and are therefore excluded.
    """
    return f"title: {chunk.filename} | text: {chunk.text}"


def _validate_vector(vector: list[float], chunk_index: int) -> None:
    """
    Raise HTTP 502 if the vector length does not match EMBEDDING_DIMENSION.

    Silent truncation or padding would corrupt Qdrant similarity searches
    once the collection is created (Layer 2.5), so we fail loudly here.
    """
    if len(vector) != settings.EMBEDDING_DIMENSION:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Embedding dimension mismatch at chunk_index={chunk_index}. "
                f"Expected {settings.EMBEDDING_DIMENSION} dimensions, "
                f"got {len(vector)}. "
                f"Check EMBEDDING_DIMENSION in config and the model's output."
            ),
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _embed_one(client: genai.Client, text: str):
    """
    Embed a single text.

    gemini-embedding-2 returns one embedding per content. A list of strings
    is treated as parts of one content, so each chunk must be sent alone.
    """
    try:
        response = client.models.embed_content(
            model=settings.GEMINI_EMBEDDING_MODEL,
            contents=[text],
            config=types.EmbedContentConfig(
                output_dimensionality=settings.EMBEDDING_DIMENSION,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Gemini embedding API error "
                f"(model={settings.GEMINI_EMBEDDING_MODEL}): "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc

    if not response.embeddings or len(response.embeddings) != 1:
        received = len(response.embeddings) if response.embeddings else 0
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Unexpected Gemini response: sent 1 text, "
                f"received {received} embedding(s)."
            ),
        )
    return response.embeddings[0]


def embed_chunks(chunks: list[DocumentChunk]) -> list[EmbeddedChunk]:
    """
    Embed a list of DocumentChunks using Gemini Embedding 2.

    Each non-empty chunk is embedded in its own API call. The embeddings
    are returned in the same order as the inputs.

    Chunks whose text is empty or whitespace-only are skipped. Layer 2.3
    already prevents empty chunks, but this is a defensive guard.

    Args:
        chunks: Chunks produced by the chunking service for one document.

    Returns:
        EmbeddedChunk for each non-empty input chunk, in the original order.

    Raises:
        HTTPException(503): GEMINI_API_KEY is not configured.
        HTTPException(400): All provided chunks are empty.
        HTTPException(502): Gemini API call failed, or returned an unexpected
                            number of embeddings, or the vector dimension does
                            not match EMBEDDING_DIMENSION.
    """
    valid_chunks = [c for c in chunks if c.text.strip()]

    if not valid_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No non-empty chunks provided for embedding.",
        )

    client = _make_client()

    result: list[EmbeddedChunk] = []
    for chunk in valid_chunks:
        content_embedding = _embed_one(client, _format_for_embedding(chunk))
        vector: list[float] = list(content_embedding.values)
        _validate_vector(vector, chunk.chunk_index)
        result.append(
            EmbeddedChunk(
                document_id=chunk.document_id,
                filename=chunk.filename,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                embedding_dimension=len(vector),
                embedding=vector,
                text=chunk.text,
            )
        )

    return result


def embed_query(query: str) -> list[float]:
    """
    Embed a search query using the asymmetric retrieval query format.

    Uses a different text prefix from document chunks to signal to the
    embedding model that this is a search query, not a document:

        task: search result | query: {query_text}

    This asymmetric format is intentional: Gemini Embedding 2 maps document
    chunks and queries into the same embedding space using different task
    prefixes, improving retrieval quality vs. symmetric embeddings.

    Args:
        query: The user's natural-language search query.

    Returns:
        A float vector of length EMBEDDING_DIMENSION.

    Raises:
        HTTPException(400): Query is empty.
        HTTPException(503): GEMINI_API_KEY is not configured.
        HTTPException(502): Gemini API call failed or returned wrong dimension.
    """
    if not query or not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty.",
        )

    client = _make_client()
    text = f"task: search result | query: {query.strip()}"

    try:
        response = client.models.embed_content(
            model=settings.GEMINI_EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=settings.EMBEDDING_DIMENSION,
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Gemini query embedding error "
                f"(model={settings.GEMINI_EMBEDDING_MODEL}): "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc

    if not response.embeddings:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gemini returned no embeddings for the query.",
        )

    vector: list[float] = list(response.embeddings[0].values)

    if len(vector) != settings.EMBEDDING_DIMENSION:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Query embedding dimension mismatch. "
                f"Expected {settings.EMBEDDING_DIMENSION}, got {len(vector)}."
            ),
        )

    return vector
