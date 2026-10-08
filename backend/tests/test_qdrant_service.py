"""
test_qdrant_service.py — Unit tests for Layer 2.5 Qdrant service.

All tests mock QdrantClient — no live Qdrant Cloud connection required.
The mock is patched at qdrant_client.QdrantClient so the service behaves
as if the SDK is present and the cluster is responding.

Tests cover:
  1. ensure_collection() creates collection with correct vector config.
  2. ensure_collection() is idempotent (no creation if already exists).
  3. ensure_collection() is a no-op when QDRANT_URL is not configured.
  4. Deterministic point_id_for() — same inputs always produce same ID.
  5. point_id_for() differs across chunk_index.
  6. point_id_for() differs across document_id.
  7. Payload contains all required fields including profile_id.
  8. profile_id is stored as a string in payload.
  9. index_embedded_chunks() calls delete before upsert (stale cleanup).
  10. index_embedded_chunks() sends correct number of points.
  11. index_embedded_chunks() raises 400 for empty chunk list.
  12. index_embedded_chunks() raises 503 when QDRANT_URL is missing.
  13. Qdrant delete failure raises 502.
  14. Qdrant upsert failure raises 502.
  15. search_chunks() builds filter with correct profile_id.
  16. search_chunks() passes top_k as limit.
  17. search_chunks() returns correctly mapped RetrievedChunk list.
  18. search_chunks() returns empty list when no results.
  19. search_chunks() raises 502 on Qdrant failure.
  20. search_chunks() raises 503 when QDRANT_URL is missing.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import HTTPException

from app.schemas.embedding import EmbeddedChunk
from app.services import qdrant_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PROFILE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SAMPLE_DOC_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
DEFAULT_DIM = 768


def make_embedded_chunk(
    chunk_index: int = 0,
    page_number: int = 1,
    text: str = "Some professional experience.",
    filename: str = "resume.pdf",
    dim: int = DEFAULT_DIM,
) -> EmbeddedChunk:
    return EmbeddedChunk(
        document_id=SAMPLE_DOC_ID,
        filename=filename,
        page_number=page_number,
        chunk_index=chunk_index,
        embedding_dimension=dim,
        embedding=[0.001 * i for i in range(dim)],
        text=text,
    )


def make_qdrant_client_mock(collection_exists: bool = False) -> MagicMock:
    """Return a mock QdrantClient where collection_exists returns the given value."""
    client = MagicMock()
    client.collection_exists.return_value = collection_exists
    return client


# ---------------------------------------------------------------------------
# 1–3. ensure_collection()
# ---------------------------------------------------------------------------

def test_ensure_collection_creates_when_absent(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_API_KEY", "test-key")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")
    monkeypatch.setattr("app.services.qdrant_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    client_mock = make_qdrant_client_mock(collection_exists=False)

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        qdrant_service.ensure_collection()

    client_mock.create_collection.assert_called_once()
    call_kwargs = client_mock.create_collection.call_args
    assert call_kwargs.kwargs["collection_name"] == "myrep_knowledge"
    vector_config = call_kwargs.kwargs["vectors_config"]
    assert vector_config.size == DEFAULT_DIM

    from qdrant_client.models import Distance
    assert vector_config.distance == Distance.COSINE


def test_ensure_collection_does_not_recreate_existing(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_API_KEY", "test-key")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    client_mock = make_qdrant_client_mock(collection_exists=True)

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        qdrant_service.ensure_collection()

    client_mock.create_collection.assert_not_called()


def test_ensure_collection_skips_when_url_not_configured(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "")

    # No QdrantClient should be constructed when URL is absent.
    with patch("qdrant_client.QdrantClient") as qdrant_cls:
        qdrant_service.ensure_collection()

    qdrant_cls.assert_not_called()


# ---------------------------------------------------------------------------
# 4–6. point_id_for() — determinism and uniqueness
# ---------------------------------------------------------------------------

def test_point_id_is_deterministic():
    id1 = qdrant_service.point_id_for(SAMPLE_DOC_ID, 3)
    id2 = qdrant_service.point_id_for(SAMPLE_DOC_ID, 3)
    assert id1 == id2


def test_point_id_differs_for_different_chunk_index():
    id1 = qdrant_service.point_id_for(SAMPLE_DOC_ID, 0)
    id2 = qdrant_service.point_id_for(SAMPLE_DOC_ID, 1)
    assert id1 != id2


def test_point_id_differs_for_different_document_id():
    other_doc = uuid.uuid4()
    id1 = qdrant_service.point_id_for(SAMPLE_DOC_ID, 0)
    id2 = qdrant_service.point_id_for(other_doc, 0)
    assert id1 != id2


def test_point_id_is_valid_uuid_string():
    pid = qdrant_service.point_id_for(SAMPLE_DOC_ID, 5)
    # Should not raise
    parsed = uuid.UUID(pid)
    assert str(parsed) == pid


# ---------------------------------------------------------------------------
# 7–8. Payload construction
# ---------------------------------------------------------------------------

def test_chunk_to_point_payload_includes_all_fields(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    chunk = make_embedded_chunk(chunk_index=7, page_number=3, text="Backend experience.", filename="cv.pdf")
    point = qdrant_service._chunk_to_point(SAMPLE_PROFILE_ID, chunk)

    payload = point.payload
    assert payload["profile_id"] == str(SAMPLE_PROFILE_ID)
    assert payload["document_id"] == str(SAMPLE_DOC_ID)
    assert payload["filename"] == "cv.pdf"
    assert payload["page_number"] == 3
    assert payload["chunk_index"] == 7
    assert payload["text"] == "Backend experience."


def test_chunk_to_point_ids_match_point_id_for():
    chunk = make_embedded_chunk(chunk_index=2)
    point = qdrant_service._chunk_to_point(SAMPLE_PROFILE_ID, chunk)
    expected_id = qdrant_service.point_id_for(SAMPLE_DOC_ID, 2)
    assert point.id == expected_id


def test_chunk_to_point_profile_id_stored_as_string():
    chunk = make_embedded_chunk()
    point = qdrant_service._chunk_to_point(SAMPLE_PROFILE_ID, chunk)
    assert isinstance(point.payload["profile_id"], str)
    assert isinstance(point.payload["document_id"], str)


# ---------------------------------------------------------------------------
# 9–14. index_embedded_chunks()
# ---------------------------------------------------------------------------

def test_index_calls_upsert_before_delete(monkeypatch):
    """Upsert must happen BEFORE stale-point delete so the index is never empty."""
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    chunks = [make_embedded_chunk(i) for i in range(3)]
    client_mock = MagicMock()
    call_order = []
    client_mock.upsert.side_effect = lambda **_: call_order.append("upsert")
    client_mock.delete.side_effect = lambda **_: call_order.append("delete")

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        qdrant_service.index_embedded_chunks(SAMPLE_PROFILE_ID, SAMPLE_DOC_ID, chunks)

    assert call_order == ["upsert", "delete"], "upsert must happen before stale-point delete"


def test_index_upserts_correct_number_of_points(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    chunks = [make_embedded_chunk(i) for i in range(5)]
    client_mock = MagicMock()

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        count = qdrant_service.index_embedded_chunks(SAMPLE_PROFILE_ID, SAMPLE_DOC_ID, chunks)

    assert count == 5
    upsert_call = client_mock.upsert.call_args
    assert len(upsert_call.kwargs["points"]) == 5


def test_index_delete_filter_uses_document_id_and_chunk_range(monkeypatch):
    """Stale-point delete must filter by document_id AND chunk_index >= new_chunk_count."""
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    chunks = [make_embedded_chunk(0), make_embedded_chunk(1)]  # 2 new chunks
    client_mock = MagicMock()

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        qdrant_service.index_embedded_chunks(SAMPLE_PROFILE_ID, SAMPLE_DOC_ID, chunks)

    delete_call = client_mock.delete.call_args
    selector = delete_call.kwargs["points_selector"]
    conditions = selector.filter.must

    # First condition: document_id match
    doc_condition = conditions[0]
    assert doc_condition.key == "document_id"
    assert doc_condition.match.value == str(SAMPLE_DOC_ID)

    # Second condition: chunk_index >= new_chunk_count (2)
    range_condition = conditions[1]
    assert range_condition.key == "chunk_index"
    assert range_condition.range.gte == 2


def test_index_raises_400_for_empty_chunks(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")

    with pytest.raises(HTTPException) as exc_info:
        qdrant_service.index_embedded_chunks(SAMPLE_PROFILE_ID, SAMPLE_DOC_ID, [])

    assert exc_info.value.status_code == 400


def test_index_raises_503_when_url_not_configured(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "")

    chunks = [make_embedded_chunk(0)]
    with pytest.raises(HTTPException) as exc_info:
        qdrant_service.index_embedded_chunks(SAMPLE_PROFILE_ID, SAMPLE_DOC_ID, chunks)

    assert exc_info.value.status_code == 503


def test_index_delete_failure_raises_502(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    client_mock = MagicMock()
    client_mock.delete.side_effect = RuntimeError("Network error")

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            qdrant_service.index_embedded_chunks(
                SAMPLE_PROFILE_ID, SAMPLE_DOC_ID, [make_embedded_chunk(0)]
            )

    assert exc_info.value.status_code == 502


def test_index_upsert_failure_raises_502(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    client_mock = MagicMock()
    client_mock.delete.return_value = None
    client_mock.upsert.side_effect = RuntimeError("Upsert failed")

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            qdrant_service.index_embedded_chunks(
                SAMPLE_PROFILE_ID, SAMPLE_DOC_ID, [make_embedded_chunk(0)]
            )

    assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# 15–20. search_chunks()
# ---------------------------------------------------------------------------

def _make_scored_point(
    doc_id: uuid.UUID,
    chunk_index: int,
    score: float = 0.9,
    text: str = "Some text.",
    filename: str = "resume.pdf",
    page_number: int = 1,
    profile_id: uuid.UUID = SAMPLE_PROFILE_ID,
) -> SimpleNamespace:
    """Build a mock ScoredPoint returned by Qdrant search."""
    return SimpleNamespace(
        id=qdrant_service.point_id_for(doc_id, chunk_index),
        score=score,
        payload={
            "profile_id": str(profile_id),
            "document_id": str(doc_id),
            "filename": filename,
            "page_number": page_number,
            "chunk_index": chunk_index,
            "text": text,
        },
    )


def test_search_includes_profile_id_filter(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    client_mock = MagicMock()
    mock_response = MagicMock()
    mock_response.points = []
    client_mock.query_points.return_value = mock_response

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        qdrant_service.search_chunks(SAMPLE_PROFILE_ID, [0.1] * DEFAULT_DIM, top_k=5)

    call_kwargs = client_mock.query_points.call_args.kwargs
    query_filter = call_kwargs["query_filter"]
    condition = query_filter.must[0]
    assert condition.key == "profile_id"
    assert condition.match.value == str(SAMPLE_PROFILE_ID)


def test_search_passes_top_k_as_limit(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    client_mock = MagicMock()
    mock_response = MagicMock()
    mock_response.points = []
    client_mock.query_points.return_value = mock_response

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        qdrant_service.search_chunks(SAMPLE_PROFILE_ID, [0.1] * DEFAULT_DIM, top_k=7)

    assert client_mock.query_points.call_args.kwargs["limit"] == 7


def test_search_returns_correct_retrieved_chunks(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    scored = _make_scored_point(
        doc_id=SAMPLE_DOC_ID,
        chunk_index=4,
        score=0.87,
        text="Managed a distributed system.",
        filename="work.pdf",
        page_number=2,
    )
    client_mock = MagicMock()
    mock_response = MagicMock()
    mock_response.points = [scored]
    client_mock.query_points.return_value = mock_response

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        results = qdrant_service.search_chunks(SAMPLE_PROFILE_ID, [0.1] * DEFAULT_DIM, top_k=5)

    assert len(results) == 1
    rc = results[0]
    assert rc.document_id == SAMPLE_DOC_ID
    assert rc.chunk_index == 4
    assert rc.score == pytest.approx(0.87)
    assert rc.text == "Managed a distributed system."
    assert rc.filename == "work.pdf"
    assert rc.page_number == 2


def test_search_returns_empty_list_when_no_results(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    client_mock = MagicMock()
    mock_response = MagicMock()
    mock_response.points = []
    client_mock.query_points.return_value = mock_response

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        results = qdrant_service.search_chunks(SAMPLE_PROFILE_ID, [0.1] * DEFAULT_DIM, top_k=5)

    assert results == []


def test_search_raises_502_on_qdrant_failure(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "https://example.qdrant.io")
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_COLLECTION", "myrep_knowledge")

    client_mock = MagicMock()
    client_mock.query_points.side_effect = RuntimeError("Connection refused")

    with patch("app.services.qdrant_service.QdrantClient", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            qdrant_service.search_chunks(SAMPLE_PROFILE_ID, [0.1] * DEFAULT_DIM, top_k=5)

    assert exc_info.value.status_code == 502


def test_search_raises_503_when_url_not_configured(monkeypatch):
    monkeypatch.setattr("app.services.qdrant_service.settings.QDRANT_URL", "")

    with pytest.raises(HTTPException) as exc_info:
        qdrant_service.search_chunks(SAMPLE_PROFILE_ID, [0.1] * DEFAULT_DIM, top_k=5)

    assert exc_info.value.status_code == 503
