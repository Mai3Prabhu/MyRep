"""
chunking_service.py — paragraph-aware, page-scoped text chunking.

This module is a pure transformation:

    list[DocumentPageText]  →  list[DocumentChunk]

It has no knowledge of the database, filesystem, HTTP, or any AI system.
This makes it straightforward to test and easy to replace in future layers.

Algorithm overview
------------------
For each page that has extractable text:

  1. Split into paragraphs at double-newline boundaries (\\n\\n or more).
     This respects the structure produced by the Layer 2.2 extraction service.

  2. Greedily group consecutive paragraphs into a chunk until the next
     paragraph would push the chunk over CHUNK_SIZE characters.

  3. If a single paragraph is itself larger than CHUNK_SIZE, split it
     further using sentence boundaries (. ! ?) first, then word boundaries
     as a fallback.  Words are never cut in half.

  4. After building the raw chunks for a page, prepend the last CHUNK_OVERLAP
     characters of the previous chunk (starting from a word boundary) to each
     subsequent chunk.  This provides carry-over context at chunk boundaries.

  5. Assign a chunk_index that increases monotonically across the entire
     document (not per-page).  The same input always produces the same indices.

Pages with has_text=False produce no chunks and are silently skipped.
"""

import re
import uuid

from app.schemas.chunking import DocumentChunk
from app.schemas.extraction import DocumentPageText


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _split_paragraphs(text: str) -> list[str]:
    """
    Split a page's text into paragraphs at any sequence of 2+ newlines.
    Empty strings and whitespace-only segments are discarded.
    """
    parts = re.split(r"\n{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def _split_at_word_boundaries(text: str, chunk_size: int) -> list[str]:
    """
    Split text into chunks of at most chunk_size characters, breaking only
    at whitespace so that no word is cut in half.
    """
    words = text.split()
    chunks: list[str] = []
    current_words: list[str] = []
    current_len = 0

    for word in words:
        # +1 accounts for the space that joins words
        added_len = len(word) + (1 if current_words else 0)
        if current_words and current_len + added_len > chunk_size:
            chunks.append(" ".join(current_words))
            current_words = [word]
            current_len = len(word)
        else:
            current_words.append(word)
            current_len += added_len

    if current_words:
        chunks.append(" ".join(current_words))

    return [c for c in chunks if c]


def _split_at_sentence_boundaries(text: str, chunk_size: int) -> list[str]:
    """
    Split text into chunks of at most chunk_size characters, preferring to
    break after sentence-ending punctuation (.  !  ?).

    If a single sentence still exceeds chunk_size, falls back to
    _split_at_word_boundaries for that sentence.
    """
    # Split on sentence-ending punctuation followed by whitespace.
    # The pattern uses a lookbehind so the delimiter stays with the sentence.
    sentence_end = re.compile(r"(?<=[.!?])\s+")
    sentences = sentence_end.split(text)

    # If the text has no sentence boundaries, go straight to word splitting.
    if len(sentences) <= 1:
        return _split_at_word_boundaries(text, chunk_size)

    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue

        if len(sentence) > chunk_size:
            # Flush current accumulator first.
            if current:
                chunks.append(current.strip())
                current = ""
            # The sentence itself is too big; fall back to word-level splitting.
            chunks.extend(_split_at_word_boundaries(sentence, chunk_size))

        elif current and len(current) + 1 + len(sentence) > chunk_size:
            chunks.append(current.strip())
            current = sentence

        else:
            current = (current + " " + sentence).lstrip() if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return [c for c in chunks if c]


def _overlap_tail(text: str, overlap_chars: int) -> str:
    """
    Return a suffix of `text` that is at most `overlap_chars` characters
    long, starting at a word boundary (never mid-word).

    Example:
        text = "Hello world foo bar"
        overlap_chars = 12
        raw tail = "o world foo bar"[-12:] → " foo bar"
        → after adjusting to word boundary → "foo bar"
    """
    if not text or overlap_chars <= 0:
        return ""

    if len(text) <= overlap_chars:
        return text

    # Take a raw slice from the end.
    raw = text[-overlap_chars:]

    # Advance past any partial word at the very start of the slice.
    first_space = raw.find(" ")
    if first_space == -1:
        # The entire overlap slice is one unbroken token; return it as-is
        # (word-boundary splitting already handled this elsewhere).
        return raw.strip()

    return raw[first_space + 1:].strip()


def _chunk_page(
    page_text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """
    Produce a list of text chunks from a single page.

    Steps:
    1. Detect paragraph boundaries.
    2. Greedily accumulate paragraphs; flush when the next paragraph would
       exceed chunk_size.
    3. Oversized paragraphs are split at sentence then word boundaries.
    4. Apply overlap: each chunk after the first is prefixed with the tail
       of the previous chunk (up to chunk_overlap characters).
    """
    paragraphs = _split_paragraphs(page_text)
    if not paragraphs:
        return []

    # --- Step 1-3: Build raw chunks without overlap ---
    raw_chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    def _flush() -> None:
        nonlocal current_parts, current_len
        if current_parts:
            raw_chunks.append("\n\n".join(current_parts))
            current_parts = []
            current_len = 0

    for para in paragraphs:
        if len(para) > chunk_size:
            # Flush whatever has accumulated before this large paragraph.
            _flush()
            raw_chunks.extend(_split_at_sentence_boundaries(para, chunk_size))
        else:
            # separator "\n\n" costs 2 characters if there is already content.
            separator_cost = 2 if current_parts else 0
            if current_len + separator_cost + len(para) > chunk_size:
                _flush()
            current_parts.append(para)
            current_len += (2 if len(current_parts) > 1 else 0) + len(para)

    _flush()

    if not raw_chunks:
        return []

    # --- Step 4: Apply overlap ---
    if chunk_overlap <= 0 or len(raw_chunks) == 1:
        return raw_chunks

    overlapped: list[str] = [raw_chunks[0]]
    for i in range(1, len(raw_chunks)):
        # How many characters can we prepend before the chunk exceeds chunk_size?
        # The "\n\n" separator between tail and raw chunk costs 2 characters.
        available_for_tail = chunk_size - len(raw_chunks[i]) - 2
        if available_for_tail <= 0:
            # The raw chunk is already at or near chunk_size; skip overlap entirely.
            overlapped.append(raw_chunks[i])
            continue

        # Cap the effective overlap to what actually fits.
        effective_overlap = min(chunk_overlap, available_for_tail)
        tail = _overlap_tail(raw_chunks[i - 1], effective_overlap)
        if tail:
            overlapped.append(tail + "\n\n" + raw_chunks[i])
        else:
            overlapped.append(raw_chunks[i])

    return overlapped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_pages(
    document_id: uuid.UUID,
    filename: str,
    pages: list[DocumentPageText],
    chunk_size: int,
    chunk_overlap: int,
) -> list[DocumentChunk]:
    """
    Transform a list of extracted pages into an ordered list of DocumentChunks.

    Guarantees:
    - Pages with has_text=False are skipped; they produce no chunks.
    - Each chunk carries full provenance: document_id, filename, page_number.
    - chunk_index increases monotonically from 0 across the entire document.
      The same input always produces the same indices (deterministic).
    - len(chunk.text) <= chunk_size for every chunk, including those with
      overlap applied. When the raw chunk is too large to accept the full
      overlap tail, the tail is silently reduced to fit. This is a strict
      invariant, not a best-effort guarantee.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap must be non-negative, got {chunk_overlap}")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be less than chunk_size ({chunk_size})"
        )

    all_chunks: list[DocumentChunk] = []
    global_index = 0

    for page in pages:
        if not page.has_text:
            continue

        page_chunk_texts = _chunk_page(page.text, chunk_size, chunk_overlap)

        for chunk_text in page_chunk_texts:
            stripped = chunk_text.strip()
            if not stripped:
                continue
            all_chunks.append(
                DocumentChunk(
                    document_id=document_id,
                    filename=filename,
                    page_number=page.page_number,
                    chunk_index=global_index,
                    text=stripped,
                )
            )
            global_index += 1

    return all_chunks
