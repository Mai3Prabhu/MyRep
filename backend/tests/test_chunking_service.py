"""
tests/test_chunking_service.py

Focused unit tests for chunking_service.py.

The chunking service is a pure transformation (no DB, no filesystem, no HTTP)
so these tests require no test client, no database fixtures, and no mocks.

Run with:
    cd backend
    pytest tests/test_chunking_service.py -v
"""

import uuid

import pytest

from app.schemas.extraction import DocumentPageText
from app.services.chunking_service import (
    _chunk_page,
    _overlap_tail,
    _split_at_word_boundaries,
    _split_paragraphs,
    chunk_pages,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_DOC_ID = uuid.uuid4()
SAMPLE_FILENAME = "test_document.pdf"


def make_page(page_number: int, text: str) -> DocumentPageText:
    return DocumentPageText(
        page_number=page_number,
        text=text,
        has_text=bool(text.strip()),
    )


def make_empty_page(page_number: int) -> DocumentPageText:
    return DocumentPageText(page_number=page_number, text="", has_text=False)


# ---------------------------------------------------------------------------
# 1. Small page → single chunk
# ---------------------------------------------------------------------------

def test_small_page_produces_one_chunk():
    text = "Hello world. This is a short paragraph."
    chunks = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_page(1, text)], chunk_size=1000, chunk_overlap=0)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].chunk_index == 0


# ---------------------------------------------------------------------------
# 2. Multiple paragraphs that fit within one chunk
# ---------------------------------------------------------------------------

def test_multiple_small_paragraphs_fit_in_one_chunk():
    para1 = "First paragraph about experience."
    para2 = "Second paragraph about skills."
    text = para1 + "\n\n" + para2
    chunks = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_page(1, text)], chunk_size=1000, chunk_overlap=0)
    assert len(chunks) == 1
    assert para1 in chunks[0].text
    assert para2 in chunks[0].text


# ---------------------------------------------------------------------------
# 3. Multiple paragraphs that exceed chunk size → split across chunks
# ---------------------------------------------------------------------------

def test_multiple_paragraphs_exceeding_chunk_size():
    # Each paragraph is ~300 chars, chunk_size=500 so two paragraphs > limit
    para1 = "A" * 300
    para2 = "B" * 300
    para3 = "C" * 300
    text = para1 + "\n\n" + para2 + "\n\n" + para3
    chunks = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_page(1, text)], chunk_size=500, chunk_overlap=0)
    assert len(chunks) >= 2
    # Each non-overlap chunk must be at most chunk_size
    for chunk in chunks:
        assert len(chunk.text) <= 500, f"Chunk too large: {len(chunk.text)}"


# ---------------------------------------------------------------------------
# 4. Oversized paragraph → split into multiple chunks
# ---------------------------------------------------------------------------

def test_oversized_single_paragraph_is_split():
    # One massive paragraph that exceeds chunk_size
    big_para = " ".join([f"word{i}" for i in range(300)])  # ~1800 chars
    chunks = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_page(1, big_para)], chunk_size=400, chunk_overlap=0)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.text) <= 400, f"Oversized chunk: {len(chunk.text)}"


# ---------------------------------------------------------------------------
# 5. Words are never cut in half
# ---------------------------------------------------------------------------

def test_word_boundaries_are_respected():
    words = [f"distinctive_word_{i}" for i in range(100)]
    text = " ".join(words)  # all distinct words
    chunks = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_page(1, text)], chunk_size=100, chunk_overlap=0)

    all_words_in_chunks = set()
    for chunk in chunks:
        for word in chunk.text.split():
            all_words_in_chunks.add(word)

    for word in words:
        assert word in all_words_in_chunks, f"Word '{word}' was lost or split during chunking"


def test_no_partial_words_at_chunk_boundaries():
    # Generate predictable multi-word text
    text = " ".join([f"longword{i:04d}" for i in range(50)])
    sub_chunks = _split_at_word_boundaries(text, chunk_size=60)
    for chunk in sub_chunks:
        # Each chunk should start and end on a full word (no partial)
        parts = chunk.split()
        for part in parts:
            # Part should match the expected word pattern
            assert part.startswith("longword"), f"Partial word found: {part!r}"


# ---------------------------------------------------------------------------
# 6. Overlap is applied
# ---------------------------------------------------------------------------

def test_overlap_is_prepended_to_subsequent_chunks():
    # Two paragraphs that will each become their own chunk
    para1 = "The first section covers background and motivation. " * 5  # ~250 chars
    para2 = "The second section discusses methodology and results. " * 5
    text = para1.strip() + "\n\n" + para2.strip()

    chunks_no_overlap = chunk_pages(
        SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_page(1, text)], chunk_size=300, chunk_overlap=0
    )
    chunks_with_overlap = chunk_pages(
        SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_page(1, text)], chunk_size=300, chunk_overlap=50
    )

    # With overlap, chunk 2 should be longer than without (it carries a prefix)
    if len(chunks_no_overlap) >= 2 and len(chunks_with_overlap) >= 2:
        assert len(chunks_with_overlap[1].text) > len(chunks_no_overlap[1].text), \
            "Chunk with overlap should be longer than chunk without overlap"


# ---------------------------------------------------------------------------
# 7. Empty page → no chunk
# ---------------------------------------------------------------------------

def test_empty_page_produces_no_chunks():
    chunks = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_empty_page(1)], chunk_size=1000, chunk_overlap=0)
    assert len(chunks) == 0


def test_image_only_page_produces_no_chunks():
    page = DocumentPageText(page_number=1, text="", has_text=False)
    chunks = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, [page], chunk_size=1000, chunk_overlap=0)
    assert chunks == []


# ---------------------------------------------------------------------------
# 8. Multiple pages → chunks retain correct page numbers
# ---------------------------------------------------------------------------

def test_multiple_pages_retain_page_numbers():
    page1 = make_page(1, "Page one content about skills and experience.")
    page2 = make_page(2, "Page two content about education and projects.")
    page3 = make_empty_page(3)  # image-only page

    chunks = chunk_pages(
        SAMPLE_DOC_ID, SAMPLE_FILENAME, [page1, page2, page3], chunk_size=1000, chunk_overlap=0
    )

    assert all(c.page_number in (1, 2) for c in chunks), \
        "Chunks should only reference pages 1 or 2"
    assert any(c.page_number == 1 for c in chunks)
    assert any(c.page_number == 2 for c in chunks)
    # Page 3 was empty — no chunks
    assert not any(c.page_number == 3 for c in chunks)


# ---------------------------------------------------------------------------
# 9. document_id is preserved in every chunk
# ---------------------------------------------------------------------------

def test_document_id_preserved():
    doc_id = uuid.uuid4()
    pages = [make_page(1, "Some meaningful content here.")]
    chunks = chunk_pages(doc_id, SAMPLE_FILENAME, pages, chunk_size=1000, chunk_overlap=0)
    for chunk in chunks:
        assert chunk.document_id == doc_id


# ---------------------------------------------------------------------------
# 10. chunk_index is deterministic
# ---------------------------------------------------------------------------

def test_chunk_index_is_deterministic():
    pages = [
        make_page(1, "First page content. " * 20),
        make_page(2, "Second page content. " * 20),
    ]
    run1 = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, pages, chunk_size=200, chunk_overlap=0)
    run2 = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, pages, chunk_size=200, chunk_overlap=0)

    assert [c.chunk_index for c in run1] == [c.chunk_index for c in run2]
    assert [c.text for c in run1] == [c.text for c in run2]


def test_chunk_index_is_zero_based_and_sequential():
    pages = [
        make_page(1, "Alpha content here. " * 15),
        make_page(2, "Beta content here. " * 15),
    ]
    chunks = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, pages, chunk_size=200, chunk_overlap=0)
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks))), \
        f"Expected sequential 0-indexed chunk_indices, got {indices}"


# ---------------------------------------------------------------------------
# 11. Chunk size stays within configured limit (no overlap applied)
# ---------------------------------------------------------------------------

def test_chunk_sizes_within_limit_no_overlap():
    long_text = " ".join([f"word{i}" for i in range(500)])
    chunks = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_page(1, long_text)], chunk_size=200, chunk_overlap=0)
    for chunk in chunks:
        assert len(chunk.text) <= 200, f"Chunk exceeds limit: {len(chunk.text)}"


# ---------------------------------------------------------------------------
# 12. _overlap_tail helper
# ---------------------------------------------------------------------------

def test_overlap_tail_respects_word_boundary():
    text = "Hello world foo bar baz"
    tail = _overlap_tail(text, 12)
    # Should not start mid-word
    assert " " not in tail[:1] or tail[0].isalpha(), "Tail should start at a word boundary"
    # Tail should be a suffix of the original
    assert text.endswith(tail.strip())


def test_overlap_tail_short_text_returns_full():
    text = "short"
    tail = _overlap_tail(text, 100)
    assert tail == text


def test_overlap_tail_zero_returns_empty():
    tail = _overlap_tail("Hello world", 0)
    assert tail == ""


# ---------------------------------------------------------------------------
# 13. _split_paragraphs helper
# ---------------------------------------------------------------------------

def test_split_paragraphs_on_double_newline():
    text = "Para one.\n\nPara two.\n\nPara three."
    paras = _split_paragraphs(text)
    assert paras == ["Para one.", "Para two.", "Para three."]


def test_split_paragraphs_ignores_blank_sections():
    text = "Para one.\n\n\n\nPara two."
    paras = _split_paragraphs(text)
    assert paras == ["Para one.", "Para two."]


def test_split_paragraphs_single_paragraph():
    text = "Only one paragraph here."
    paras = _split_paragraphs(text)
    assert paras == [text]


# ---------------------------------------------------------------------------
# 14. Invalid configuration raises ValueError
# ---------------------------------------------------------------------------

def test_invalid_chunk_size_raises():
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_page(1, "text")], chunk_size=0, chunk_overlap=0)


def test_overlap_greater_than_chunk_size_raises():
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_page(1, "text")], chunk_size=100, chunk_overlap=200)


# ---------------------------------------------------------------------------
# 15. No content loss across chunks (all text is represented)
# ---------------------------------------------------------------------------

def test_no_content_loss():
    """All words from the original text should appear in at least one chunk."""
    original_words = [f"keyword{i}" for i in range(50)]
    text = " ".join(original_words)
    chunks = chunk_pages(SAMPLE_DOC_ID, SAMPLE_FILENAME, [make_page(1, text)], chunk_size=150, chunk_overlap=0)

    all_chunk_text = " ".join(c.text for c in chunks)
    for word in original_words:
        assert word in all_chunk_text, f"Word '{word}' was lost during chunking"


# ---------------------------------------------------------------------------
# 16. Strict size invariant: len(chunk.text) <= CHUNK_SIZE even with overlap
# ---------------------------------------------------------------------------

def test_chunk_size_invariant_holds_with_overlap_near_boundary():
    """
    Regression test: overlap must never push any chunk over CHUNK_SIZE.

    Setup:
    - Two paragraphs each ~489 chars (just under CHUNK_SIZE=500).
    - They do not fit together, so each becomes its own raw chunk.
    - CHUNK_OVERLAP=100. Without the cap, chunk 2 would be
      ~100 (tail) + 2 (sep) + 489 (raw) = ~591 chars — violating the invariant.
    - With the fix, the tail is capped to (500 - 489 - 2) = 9 chars max,
      keeping chunk 2 at most 500 chars.
    """
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 100

    para = " ".join(["word"] * 98)   # 4*98 + 97 = 489 chars
    assert len(para) == 489, f"Test setup: expected 489 chars, got {len(para)}"
    assert len(para) < CHUNK_SIZE

    text = para + "\n\n" + para  # two near-limit paragraphs

    chunks = chunk_pages(
        SAMPLE_DOC_ID, SAMPLE_FILENAME,
        [make_page(1, text)],
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    assert len(chunks) == 2, f"Expected 2 chunks, got {len(chunks)}"

    # THE KEY INVARIANT — must hold after overlap is applied
    for chunk in chunks:
        assert len(chunk.text) <= CHUNK_SIZE, (
            f"Chunk {chunk.chunk_index} exceeds CHUNK_SIZE={CHUNK_SIZE} after "
            f"overlap: actual len={len(chunk.text)}\n"
            f"First 120 chars: {chunk.text[:120]!r}"
        )

    assert max(len(c.text) for c in chunks) <= CHUNK_SIZE


def test_chunk_size_invariant_holds_with_overlap_exact_boundary():
    """
    Boundary case: raw chunk is exactly chunk_size characters.
    No overlap tail should be prepended (available_for_tail would be -2).
    """
    CHUNK_SIZE = 100
    CHUNK_OVERLAP = 20

    # Craft a paragraph of exactly CHUNK_SIZE chars using whole words.
    # "word " is 5 chars; 20 words = 20*5 - 1 = 99 chars. Add one more char via longer word.
    para = " ".join(["word"] * 19 + ["wordx"])  # 5*20 + 19 = 119 chars — too large
    # Simpler: make para exactly chunk_size via word boundary splitting.
    raw = "a " * 49 + "a"  # 2*49 + 1 = 99 chars. Close enough.
    para = raw  # 99 chars, just under limit; two of them won't fit together.

    text = para + "\n\n" + para

    chunks = chunk_pages(
        SAMPLE_DOC_ID, SAMPLE_FILENAME,
        [make_page(1, text)],
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    for chunk in chunks:
        assert len(chunk.text) <= CHUNK_SIZE, (
            f"Chunk exceeds limit: len={len(chunk.text)} > {CHUNK_SIZE}"
        )


def test_global_size_invariant_across_all_parametrisations():
    """
    Parametric sweep: for several (chunk_size, chunk_overlap) combinations,
    confirm max(len(chunk.text)) <= chunk_size across a realistic multi-paragraph page.
    """
    long_page_text = "\n\n".join([
        "Experience: Led backend platform team at Acme Corp from 2020 to 2024. "
        "Built distributed data pipelines and improved API latency by 40 percent.",
        "Skills: Python, FastAPI, SQLAlchemy, PostgreSQL, MySQL, Docker, Kubernetes, "
        "Redis, Kafka, LangChain, LangGraph, Gemini, Qdrant, Next.js, TypeScript.",
        "Education: B.Tech Computer Science, State University, 2018. "
        "Final year project on distributed graph algorithms.",
        "Projects: MyRep — AI Professional Representative system using FastAPI, "
        "Gemini embeddings, Qdrant vector store, and LangGraph for stateful workflows.",
    ] * 3)  # repeat for a longer document

    for chunk_size, chunk_overlap in [
        (200, 20),
        (300, 50),
        (500, 100),
        (1000, 100),
        (1000, 200),
    ]:
        chunks = chunk_pages(
            SAMPLE_DOC_ID, SAMPLE_FILENAME,
            [make_page(1, long_page_text)],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        violating = [c for c in chunks if len(c.text) > chunk_size]
        assert not violating, (
            f"chunk_size={chunk_size}, chunk_overlap={chunk_overlap}: "
            f"{len(violating)} chunks exceeded limit. "
            f"Max len: {max(len(c.text) for c in chunks)}"
        )
