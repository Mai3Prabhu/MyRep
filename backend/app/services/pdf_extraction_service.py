"""
pdf_extraction_service.py — page-aware text extraction from PDF files.

This service's only responsibility is to open a PDF from disk and extract
text page-by-page. It does not interact with the database, network, or any
AI system.

The output is designed for consumption by the future Layer 2.3 chunking
service. Each page carries its page_number so that chunk metadata can be
traced back to the source document and page.
"""

import re
from pathlib import Path

from fastapi import HTTPException, status

import pypdf
from pypdf.errors import PdfReadError

from app.schemas.extraction import DocumentPageText


def _normalize_text(raw: str) -> str:
    """
    Apply minimal whitespace normalization to extracted page text.

    Rules applied (in order):
    1. Strip trailing whitespace from each line — pypdf often emits
       lines with trailing spaces due to PDF coordinate-based layout.
    2. Collapse runs of 3 or more consecutive blank lines to 2 —
       preserves intentional paragraph spacing while removing excessive gaps.
    3. Strip leading/trailing whitespace from the full text.

    Intentionally NOT done:
    - Collapsing multiple spaces within a line (could destroy table formatting)
    - Removing meaningful punctuation or structural characters
    - Any form of summarisation or LLM post-processing
    """
    lines = raw.split("\n")

    # Strip trailing whitespace per line
    lines = [line.rstrip() for line in lines]

    # Collapse 3+ consecutive blank lines to 2
    normalized: list[str] = []
    consecutive_blanks = 0
    for line in lines:
        if line.strip() == "":
            consecutive_blanks += 1
            if consecutive_blanks <= 2:
                normalized.append(line)
        else:
            consecutive_blanks = 0
            normalized.append(line)

    return "\n".join(normalized).strip()


def extract_pages(pdf_path: Path) -> list[DocumentPageText]:
    """
    Extract text from every page of a PDF and return structured page objects.

    Each returned DocumentPageText carries:
    - page_number: 1-indexed page position (matches human page numbering)
    - text: normalized extracted text (empty string if no text found)
    - has_text: False if the page yielded no extractable text, which
      indicates an image-only or scanned page — OCR is a future layer

    Raises HTTPException on:
    - File not found (500 — server-side storage problem)
    - Encrypted / password-protected PDF (422)
    - Corrupt or unreadable PDF (422)
    - Unexpected I/O errors (500)
    """
    if not pdf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "The stored PDF file could not be found. "
                "It may have been moved or deleted from local storage."
            ),
        )

    try:
        reader = pypdf.PdfReader(str(pdf_path))
    except PdfReadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unable to read PDF. The file may be corrupt or malformed.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while opening the PDF file.",
        ) from exc

    # Reject password-protected PDFs — we cannot extract text without the key.
    if reader.is_encrypted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Cannot extract text from a password-protected PDF. "
                "Please provide an unlocked version."
            ),
        )

    pages: list[DocumentPageText] = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            raw_text: str = page.extract_text() or ""
        except Exception:
            # pypdf can raise on certain malformed page streams;
            # treat as an empty page rather than failing the entire extraction.
            raw_text = ""

        normalized = _normalize_text(raw_text)

        pages.append(
            DocumentPageText(
                page_number=page_number,
                text=normalized,
                has_text=bool(normalized),
            )
        )

    return pages
