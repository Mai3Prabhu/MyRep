"""
test_embedding_service.py — Unit tests for Layer 2.4 embedding service.

All tests mock the Gemini client — no real API key is required.
The mock is patched at the google.genai.Client level so the service
behaves as if the SDK is present and responding.

Test numbering follows the Layer 2.4 spec:
  1. Correct model is read from configuration.
  2. Correct dimension is passed to EmbedContentConfig.
  3. Correct document format: title: filename | text: chunk.
  4. Empty chunks are rejected.
  5. Returned vector dimension is validated.
  6. Dimension mismatch raises a clear error.
  7. Multiple chunks each get their own embedding API call.
  8. API failures are handled without leaking credentials.
  9–11. Existing chunking/extraction tests still pass (covered by their own
        test files; importing embed_chunks here verifies the import graph).

Additionally tests:
  - Missing GEMINI_API_KEY raises HTTP 503.
  - Single empty chunk in a list of valid chunks is skipped.
  - Response embedding count mismatch raises HTTP 502.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.chunking import DocumentChunk
from app.schemas.embedding import EmbeddedChunk
from app.services import embedding_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_DOC_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")
SAMPLE_FILENAME = "resume.pdf"
DEFAULT_DIM = 768   # must match settings.EMBEDDING_DIMENSION default


def make_chunk(
    text: str = "Some professional experience text.",
    chunk_index: int = 0,
    page_number: int = 1,
    filename: str = SAMPLE_FILENAME,
) -> DocumentChunk:
    return DocumentChunk(
        document_id=SAMPLE_DOC_ID,
        filename=filename,
        page_number=page_number,
        chunk_index=chunk_index,
        text=text,
    )


def fake_embedding(dim: int = DEFAULT_DIM) -> SimpleNamespace:
    """Return a mock ContentEmbedding with `dim` float values."""
    return SimpleNamespace(values=[0.001 * i for i in range(dim)])


def mock_embed_response(num_chunks: int, dim: int = DEFAULT_DIM) -> MagicMock:
    """
    Return a mock EmbedContentResponse whose `embeddings` attribute
    contains `num_chunks` fake embeddings of `dim` dimensions each.
    """
    response = MagicMock()
    response.embeddings = [fake_embedding(dim) for _ in range(num_chunks)]
    return response


def make_client_mock(response: MagicMock) -> MagicMock:
    """
    Build a mock genai.Client where client.models.embed_content returns
    the given response.
    """
    client = MagicMock()
    client.models.embed_content.return_value = response
    return client


# ---------------------------------------------------------------------------
# 1. Correct model is read from configuration
# ---------------------------------------------------------------------------

def test_correct_model_used(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunk = make_chunk()
    response = mock_embed_response(1)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        embedding_service.embed_chunks([chunk])

    call_kwargs = client_mock.models.embed_content.call_args
    assert call_kwargs.kwargs["model"] == "gemini-embedding-2"


# ---------------------------------------------------------------------------
# 2. Correct dimension is passed to EmbedContentConfig
# ---------------------------------------------------------------------------

def test_correct_dimension_passed(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunk = make_chunk()
    response = mock_embed_response(1)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        embedding_service.embed_chunks([chunk])

    call_kwargs = client_mock.models.embed_content.call_args
    config = call_kwargs.kwargs["config"]
    assert config.output_dimensionality == DEFAULT_DIM


# ---------------------------------------------------------------------------
# 3. Correct document format: title: filename | text: chunk_text
# ---------------------------------------------------------------------------

def test_document_format(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunk = make_chunk(text="MindMate uses FastAPI for the backend API.", filename="MindMate.pdf")
    expected_text = "title: MindMate.pdf | text: MindMate uses FastAPI for the backend API."

    response = mock_embed_response(1)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        embedding_service.embed_chunks([chunk])

    call_kwargs = client_mock.models.embed_content.call_args
    contents = call_kwargs.kwargs["contents"]
    assert contents == [expected_text], (
        f"Expected formatted document text, got: {contents}"
    )


def test_document_format_excludes_metadata_fields(monkeypatch):
    """document_id, page_number, chunk_index must NOT appear in the embedded text."""
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunk = make_chunk(text="Some text.", chunk_index=7, page_number=3)
    response = mock_embed_response(1)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        embedding_service.embed_chunks([chunk])

    call_kwargs = client_mock.models.embed_content.call_args
    embedded_text: str = call_kwargs.kwargs["contents"][0]

    assert str(SAMPLE_DOC_ID) not in embedded_text, "document_id must not appear in embedded text"
    assert "page_number" not in embedded_text
    assert "chunk_index" not in embedded_text
    assert "7" not in embedded_text, "chunk_index value must not appear in embedded text"
    assert "3" not in embedded_text, "page_number value must not appear in embedded text"


# ---------------------------------------------------------------------------
# 4. Empty chunks are rejected
# ---------------------------------------------------------------------------

def test_all_empty_chunks_raises_400(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")

    empty_chunks = [
        make_chunk(text=""),
        make_chunk(text="   "),
        make_chunk(text="\t\n"),
    ]

    with pytest.raises(HTTPException) as exc_info:
        embedding_service.embed_chunks(empty_chunks)

    assert exc_info.value.status_code == 400


def test_empty_list_raises_400(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")

    with pytest.raises(HTTPException) as exc_info:
        embedding_service.embed_chunks([])

    assert exc_info.value.status_code == 400


def test_mixed_empty_and_valid_chunks_skips_empty(monkeypatch):
    """Empty chunks in a mixed list are silently skipped; valid ones are embedded."""
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunks = [
        make_chunk(text="Valid chunk text.", chunk_index=0),
        make_chunk(text="", chunk_index=1),          # empty — should be skipped
        make_chunk(text="Another valid chunk.", chunk_index=2),
    ]
    # One embedding per call. Empty chunks are not sent.
    response = mock_embed_response(1)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        result = embedding_service.embed_chunks(chunks)

    # Only the two valid chunks should be embedded.
    assert len(result) == 2
    assert client_mock.models.embed_content.call_count == 2
    for call in client_mock.models.embed_content.call_args_list:
        assert len(call.kwargs["contents"]) == 1


# ---------------------------------------------------------------------------
# 5 & 6. Returned vector dimension validated; mismatch raises clear error
# ---------------------------------------------------------------------------

def test_correct_dimension_accepted(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunk = make_chunk()
    response = mock_embed_response(1, dim=DEFAULT_DIM)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        result = embedding_service.embed_chunks([chunk])

    assert len(result) == 1
    assert result[0].embedding_dimension == DEFAULT_DIM
    assert len(result[0].embedding) == DEFAULT_DIM


def test_dimension_mismatch_raises_502(monkeypatch):
    """If Gemini returns a different dimension, raise HTTP 502 immediately."""
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunk = make_chunk()
    wrong_dim = DEFAULT_DIM + 100   # 868, not 768
    response = mock_embed_response(1, dim=wrong_dim)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            embedding_service.embed_chunks([chunk])

    assert exc_info.value.status_code == 502
    assert str(DEFAULT_DIM) in exc_info.value.detail
    assert str(wrong_dim) in exc_info.value.detail


def test_dimension_mismatch_error_mentions_chunk_index(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunk = make_chunk(chunk_index=5)
    response = mock_embed_response(1, dim=100)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            embedding_service.embed_chunks([chunk])

    assert "chunk_index=5" in exc_info.value.detail


# ---------------------------------------------------------------------------
# 7. Each chunk is embedded in its own API call
# ---------------------------------------------------------------------------

def test_multiple_chunks_one_call_each(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunks = [
        make_chunk(text=f"Chunk {i} with enough text.", chunk_index=i)
        for i in range(5)
    ]
    response = mock_embed_response(1)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        result = embedding_service.embed_chunks(chunks)

    # gemini-embedding-2 accepts one content per request.
    assert client_mock.models.embed_content.call_count == 5

    # All five chunks returned.
    assert len(result) == 5

    sent = [
        call.kwargs["contents"][0]
        for call in client_mock.models.embed_content.call_args_list
    ]
    assert len(sent) == 5
    assert all(text.startswith("title: ") for text in sent)


def test_batch_order_preserved(monkeypatch):
    """chunk_index in the output must match the input order."""
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunks = [make_chunk(text=f"Text {i}.", chunk_index=i) for i in range(3)]
    response = mock_embed_response(1)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        result = embedding_service.embed_chunks(chunks)

    assert [r.chunk_index for r in result] == [0, 1, 2]


# ---------------------------------------------------------------------------
# 8. API failures handled without leaking credentials
# ---------------------------------------------------------------------------

def test_gemini_api_error_raises_502(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunk = make_chunk()
    client_mock = MagicMock()
    client_mock.models.embed_content.side_effect = RuntimeError("Connection refused")

    with patch("google.genai.Client", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            embedding_service.embed_chunks([chunk])

    assert exc_info.value.status_code == 502


def test_api_error_does_not_leak_api_key(monkeypatch):
    """The API key must never appear in error messages."""
    secret_key = "super-secret-api-key-abc123"
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", secret_key)
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunk = make_chunk()
    client_mock = MagicMock()
    client_mock.models.embed_content.side_effect = Exception("some Gemini error")

    with patch("google.genai.Client", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            embedding_service.embed_chunks([chunk])

    assert secret_key not in exc_info.value.detail


def test_unexpected_embedding_count_raises_502(monkeypatch):
    """If Gemini returns more than one embedding for a single chunk, raise HTTP 502."""
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunks = [make_chunk(chunk_index=i) for i in range(3)]
    response = mock_embed_response(2)   # 2 back for 1 sent
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            embedding_service.embed_chunks(chunks)

    assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# Missing GEMINI_API_KEY raises HTTP 503
# ---------------------------------------------------------------------------

def test_missing_api_key_raises_503(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "")

    chunk = make_chunk()
    with pytest.raises(HTTPException) as exc_info:
        embedding_service.embed_chunks([chunk])

    assert exc_info.value.status_code == 503
    assert "GEMINI_API_KEY" in exc_info.value.detail


def test_whitespace_api_key_raises_503(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "   ")

    chunk = make_chunk()
    with pytest.raises(HTTPException) as exc_info:
        embedding_service.embed_chunks([chunk])

    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Return type and provenance correctness
# ---------------------------------------------------------------------------

def test_embedded_chunk_carries_full_provenance(monkeypatch):
    """EmbeddedChunk must carry document_id, filename, page_number, chunk_index."""
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    doc_id = uuid.uuid4()
    chunk = DocumentChunk(
        document_id=doc_id,
        filename="cv.pdf",
        page_number=4,
        chunk_index=11,
        text="Professional summary section with relevant experience.",
    )
    response = mock_embed_response(1)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        result = embedding_service.embed_chunks([chunk])

    ec: EmbeddedChunk = result[0]
    assert ec.document_id == doc_id
    assert ec.filename == "cv.pdf"
    assert ec.page_number == 4
    assert ec.chunk_index == 11
    assert ec.embedding_dimension == DEFAULT_DIM
    assert len(ec.embedding) == DEFAULT_DIM


def test_embedding_values_are_floats(monkeypatch):
    monkeypatch.setattr("app.services.embedding_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.embedding_service.settings.EMBEDDING_DIMENSION", DEFAULT_DIM)

    chunk = make_chunk()
    response = mock_embed_response(1)
    client_mock = make_client_mock(response)

    with patch("google.genai.Client", return_value=client_mock):
        result = embedding_service.embed_chunks([chunk])

    assert all(isinstance(v, float) for v in result[0].embedding)


# ---------------------------------------------------------------------------
# Internal helper: _format_for_embedding
# ---------------------------------------------------------------------------

def test_format_for_embedding_structure():
    chunk = make_chunk(text="Deep learning experience.", filename="portfolio.pdf")
    formatted = embedding_service._format_for_embedding(chunk)
    assert formatted == "title: portfolio.pdf | text: Deep learning experience."


def test_format_for_embedding_uses_filename_not_id():
    chunk = make_chunk(text="Some text.")
    formatted = embedding_service._format_for_embedding(chunk)
    assert str(SAMPLE_DOC_ID) not in formatted
    assert SAMPLE_FILENAME in formatted


# ---------------------------------------------------------------------------
# Internal helper: _format_for_embedding (query format is NOT implemented)
# ---------------------------------------------------------------------------

def test_query_embedding_function_exists():
    """
    Layer 2.6 introduced embed_query. Verify it is present and is a function.
    (This replaces the Layer 2.4 guard that asserted it did NOT exist.)
    """
    assert hasattr(embedding_service, "embed_query"), (
        "embed_query should be implemented in Layer 2.6"
    )
    assert callable(embedding_service.embed_query)
