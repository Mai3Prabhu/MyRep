import uuid

from pydantic import BaseModel


class DocumentPageText(BaseModel):
    """
    Extracted text for a single page of a PDF.

    page_number is 1-indexed to match human expectations (page 1 = first page).

    has_text is False when pypdf extracted no text from the page.
    This typically indicates a scanned/image-only page. The text field will
    be an empty string in that case. No fabricated or OCR-generated text
    is ever placed here; OCR is a future capability.

    This structure carries the provenance the future chunking layer needs:
        document_id + page_number → chunk origin metadata
    """

    page_number: int
    text: str
    has_text: bool


class DocumentExtractionResponse(BaseModel):
    """
    Full extraction result for one document.

    Preserves document identity (document_id, filename) alongside each page
    so consumers never need to look up these values separately.

    The future chunking layer will consume:
        pages[] → chunks with metadata (document_id, page_number, chunk_index)
    """

    document_id: uuid.UUID
    filename: str
    page_count: int
    pages: list[DocumentPageText]
