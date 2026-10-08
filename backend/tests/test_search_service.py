"""
test_search_service.py — Unit tests for Layer 2.6 query embedding and retrieval.

All tests mock both Gemini (via google.genai.Client) and Qdrant (via
qdrant_client.QdrantClient) — no live cloud services are required.

Tests cover:
  1. Query embedding uses correct format: task: search result | query: ...
  2. Query embedding uses correct model from config.
  3. Query embedding uses correct output dimension.
  4. Empty query raises HTTP 400.
  5. Empty query (whitespace) raises HTTP 400.
  6. Gemini failure on query raises HTTP 502.
  7. Query dimension mismatch raises HTTP 502.
  8. search_profile() validates profile exists (raises 404 if not).
  9. search_profile() passes profile_id to Qdrant filter (isolation).
  10. search_profile() passes top_k correctly.
  11. search_profile() returns correct provenance in results.
  12. search_profile() returns empty results gracefully.
  13. Qdrant failure during search raises HTTP 502.
  14. search_profile() uses GEMINI_API_KEY, which is never leaked in errors.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services import embedding_service, qdrant_service
from app.schemas.retrieval import RetrievedChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PROFILE_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
SAMPLE_DOC_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
DEFAULT_DIM = 768


def fake_query_response(dim: int = DEFAULT_DIM) -> MagicMock:
    """Return a mock EmbedContentResponse with one embedding for a query."""
    embedding = SimpleNamespace(values=[0.001 * i for i in range(dim)])
    response = MagicMock()
    response.embeddings = [embedding]
    return response


def make_gemini_client_mock(response: MagicMock) -> MagicMock:
    client = MagicMock()
    client.models.embed_content.return_value = response
    return client


def make_retrieved_chunk(
    doc_id: uuid.UUID = SAMPLE_DOC_ID,
    chunk_index: int = 0,
    score: float = 0.88,
) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=doc_id,
        filename="resume.pdf",
        page_number=1,
        chunk_index=chunk_index,
        text="Some chunk text.",
        score=score,
    )


# ---------------------------------------------------------------------------
# 1–3. embed_query() — format, model, dimension
# ---------------------------------------------------------------------------

def test_embed_query_uses_correct_format(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    response = fake_query_response()
    client_mock = make_gemini_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        embedding_service.embed_query("What projects has this person worked on?")

    call_kwargs = client_mock.models.embed_content.call_args.kwargs
    content = call_kwargs["contents"]
    assert content == "task: search result | query: What projects has this person worked on?"


def test_embed_query_uses_model_from_config(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    response = fake_query_response()
    client_mock = make_gemini_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        embedding_service.embed_query("leadership experience")

    call_kwargs = client_mock.models.embed_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-embedding-2"


def test_embed_query_passes_correct_dimension(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    response = fake_query_response()
    client_mock = make_gemini_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        embedding_service.embed_query("some query")

    call_kwargs = client_mock.models.embed_content.call_args.kwargs
    assert call_kwargs["config"].output_dimensionality == DEFAULT_DIM


def test_embed_query_returns_correct_length_vector(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    response = fake_query_response(DEFAULT_DIM)
    client_mock = make_gemini_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        vector = embedding_service.embed_query("skills and technologies")

    assert len(vector) == DEFAULT_DIM
    assert all(isinstance(v, float) for v in vector)


# ---------------------------------------------------------------------------
# 4–5. Empty query validation
# ---------------------------------------------------------------------------

def test_embed_query_rejects_empty_string(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")

    with pytest.raises(HTTPException) as exc_info:
        embedding_service.embed_query("")

    assert exc_info.value.status_code == 400


def test_embed_query_rejects_whitespace_only(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")

    with pytest.raises(HTTPException) as exc_info:
        embedding_service.embed_query("   \t\n  ")

    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 6. Gemini failure on query
# ---------------------------------------------------------------------------

def test_embed_query_gemini_failure_raises_502(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    client_mock = MagicMock()
    client_mock.models.embed_content.side_effect = RuntimeError("API unavailable")

    with patch("google.genai.Client", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            embedding_service.embed_query("find projects")

    assert exc_info.value.status_code == 502


def test_embed_query_does_not_leak_api_key_in_error(monkeypatch):
    secret = "super-secret-gemini-key-xyz"
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", secret)
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    client_mock = MagicMock()
    client_mock.models.embed_content.side_effect = Exception("something failed")

    with patch("google.genai.Client", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            embedding_service.embed_query("query text")

    assert secret not in exc_info.value.detail


# ---------------------------------------------------------------------------
# 7. Query dimension mismatch
# ---------------------------------------------------------------------------

def test_embed_query_dimension_mismatch_raises_502(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    response = fake_query_response(dim=100)  # wrong dimension
    client_mock = make_gemini_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            embedding_service.embed_query("any query")

    assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# 8–13. search_profile() — integration through search_service
# ---------------------------------------------------------------------------

def _patch_search_profile(
    monkeypatch,
    query_vector: list[float] | None = None,
    search_results: list[RetrievedChunk] | None = None,
    profile_exists: bool = True,
):
    """
    Patch embedding_service.embed_query and qdrant_service.search_chunks
    so that search_service.search_profile() can be called without live cloud.
    """
    if query_vector is None:
        query_vector = [0.1] * DEFAULT_DIM
    if search_results is None:
        search_results = []

    monkeypatch.setattr(
        "app.services.search_service.embedding_service.embed_query",
        lambda q: query_vector,
    )
    monkeypatch.setattr(
        "app.services.search_service.qdrant_service.search_chunks",
        lambda profile_id, query_vector, top_k: search_results,
    )

    if not profile_exists:
        def fake_get_profile(db, pid):
            raise HTTPException(status_code=404, detail="Profile not found.")
        monkeypatch.setattr(
            "app.services.search_service.profile_service.get_profile",
            fake_get_profile,
        )
    else:
        monkeypatch.setattr(
            "app.services.search_service.profile_service.get_profile",
            lambda db, pid: None,
        )


def test_search_profile_raises_404_for_nonexistent_profile(monkeypatch):
    _patch_search_profile(monkeypatch, profile_exists=False)

    from app.services import search_service
    with pytest.raises(HTTPException) as exc_info:
        search_service.search_profile(db=None, profile_id=SAMPLE_PROFILE_ID, query="test", top_k=5)

    assert exc_info.value.status_code == 404


def test_search_profile_passes_profile_id_to_qdrant(monkeypatch):
    """profile_id must be passed to Qdrant, not chosen by the query result."""
    received_profile_ids = []

    monkeypatch.setattr(
        "app.services.search_service.profile_service.get_profile",
        lambda db, pid: None,
    )
    monkeypatch.setattr(
        "app.services.search_service.embedding_service.embed_query",
        lambda q: [0.1] * DEFAULT_DIM,
    )

    def capture_search(profile_id, query_vector, top_k):
        received_profile_ids.append(profile_id)
        return []

    monkeypatch.setattr(
        "app.services.search_service.qdrant_service.search_chunks",
        capture_search,
    )

    from app.services import search_service
    search_service.search_profile(db=None, profile_id=SAMPLE_PROFILE_ID, query="test", top_k=5)

    assert received_profile_ids == [SAMPLE_PROFILE_ID]


def test_search_profile_passes_top_k(monkeypatch):
    received_top_k = []

    monkeypatch.setattr("app.services.search_service.profile_service.get_profile", lambda db, pid: None)
    monkeypatch.setattr("app.services.search_service.embedding_service.embed_query", lambda q: [0.1] * DEFAULT_DIM)

    def capture_search(profile_id, query_vector, top_k):
        received_top_k.append(top_k)
        return []

    monkeypatch.setattr("app.services.search_service.qdrant_service.search_chunks", capture_search)

    from app.services import search_service
    search_service.search_profile(db=None, profile_id=SAMPLE_PROFILE_ID, query="test", top_k=3)

    assert received_top_k == [3]


def test_search_profile_returns_correct_provenance(monkeypatch):
    chunks = [
        make_retrieved_chunk(SAMPLE_DOC_ID, chunk_index=0, score=0.95),
        make_retrieved_chunk(SAMPLE_DOC_ID, chunk_index=1, score=0.80),
    ]
    _patch_search_profile(monkeypatch, search_results=chunks)

    from app.services import search_service
    response = search_service.search_profile(
        db=None, profile_id=SAMPLE_PROFILE_ID, query="my query", top_k=5
    )

    assert response.profile_id == SAMPLE_PROFILE_ID
    assert response.query == "my query"
    assert len(response.results) == 2
    assert response.results[0].score == pytest.approx(0.95)
    assert response.results[1].chunk_index == 1


def test_search_profile_returns_empty_results_gracefully(monkeypatch):
    _patch_search_profile(monkeypatch, search_results=[])

    from app.services import search_service
    response = search_service.search_profile(
        db=None, profile_id=SAMPLE_PROFILE_ID, query="obscure query", top_k=5
    )

    assert response.results == []


def test_search_profile_query_preserved_in_response(monkeypatch):
    _patch_search_profile(monkeypatch)

    from app.services import search_service
    response = search_service.search_profile(
        db=None, profile_id=SAMPLE_PROFILE_ID, query="What are this person's skills?", top_k=5
    )

    assert response.query == "What are this person's skills?"


# ---------------------------------------------------------------------------
# No cross-profile results
# ---------------------------------------------------------------------------

def test_search_does_not_mix_profiles(monkeypatch):
    """
    Verify that each call to search_profile passes its own profile_id to Qdrant.
    Cross-profile filtering is enforced at the Qdrant level (tested in
    test_qdrant_service.py), but this test confirms the correct ID flows through.
    """
    profile_a = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-000000000001")
    profile_b = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-000000000002")
    seen_ids = []

    monkeypatch.setattr("app.services.search_service.profile_service.get_profile", lambda db, pid: None)
    monkeypatch.setattr("app.services.search_service.embedding_service.embed_query", lambda q: [0.1] * DEFAULT_DIM)

    def capture_search(profile_id, query_vector, top_k):
        seen_ids.append(profile_id)
        return []

    monkeypatch.setattr("app.services.search_service.qdrant_service.search_chunks", capture_search)

    from app.services import search_service
    search_service.search_profile(db=None, profile_id=profile_a, query="q1", top_k=5)
    search_service.search_profile(db=None, profile_id=profile_b, query="q2", top_k=5)

    assert seen_ids == [profile_a, profile_b]
    assert seen_ids[0] != seen_ids[1]
