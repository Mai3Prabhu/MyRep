"""Fixture corpus for Layer 8 evaluation. Not a Qdrant dump."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.schemas.retrieval import RetrievedChunk, SearchResponse

PROFILE_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PROFILE_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
DOC_A = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
DOC_B = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
DOC_CONFLICT = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


@dataclass(frozen=True)
class FixtureChunk:
    profile_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int
    chunk_index: int
    text: str
    tags: tuple[str, ...]


CORPUS: tuple[FixtureChunk, ...] = (
    FixtureChunk(
        PROFILE_A, DOC_A, "resume.pdf", 1, 0,
        "Maitri built professional projects including MindMate, an AI application using Next.js, FastAPI, and PostgreSQL.",
        ("mindmate", "fastapi", "postgresql", "next.js", "projects", "maitri"),
    ),
    FixtureChunk(
        PROFILE_A, DOC_A, "resume.pdf", 1, 1,
        "She also built Insightify, an analytics dashboard.",
        ("insightify", "projects", "analytics"),
    ),
    FixtureChunk(
        PROFILE_A, DOC_A, "projects.pdf", 2, 0,
        "MindMate's API is implemented with FastAPI because it is typed and fast.",
        ("mindmate", "fastapi", "backend"),
    ),
    FixtureChunk(
        PROFILE_A, DOC_CONFLICT, "notes.pdf", 1, 0,
        "MindMate's backend is implemented with Flask.",
        ("mindmate", "flask", "backend", "conflict"),
    ),
    FixtureChunk(
        PROFILE_A, DOC_A, "resume.pdf", 2, 0,
        "Maitri is an AI engineer. Skills include Python and TypeScript.",
        ("skills", "python", "typescript", "maitri"),
    ),
    FixtureChunk(
        PROFILE_B, DOC_B, "other.pdf", 1, 0,
        "FlameCast uses Kafka for event streaming. This belongs only to profile B.",
        ("flamecast", "kafka"),
    ),
)


_STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "been", "being", "but", "by",
    "can", "did", "do", "does", "for", "from", "had", "has", "have",
    "he", "her", "his", "how", "i", "in", "is", "it", "its", "listed",
    "me", "not", "of", "on", "or", "she", "tell", "that", "the", "their",
    "them", "they", "this", "those", "these", "to", "use", "used", "using",
    "was", "we", "were", "what", "when", "where", "which", "who", "why",
    "with", "you", "about",
}


def fixture_search(profile_id: uuid.UUID, query: str, top_k: int = 5) -> SearchResponse:
    """
    Keyword overlap over the fixture corpus, filtered by profile_id.

    This is NOT Qdrant cosine search and is NOT production retrieval accuracy.
    """
    tokens = {t for t in _tokenize(query) if len(t) > 1 and t not in _STOPWORDS}
    scored: list[tuple[float, FixtureChunk]] = []
    for chunk in CORPUS:
        if chunk.profile_id != profile_id:
            continue
        haystack = set(_tokenize(chunk.text)).union(chunk.tags)
        overlap = tokens.intersection(haystack)
        if not overlap:
            continue
        score = len(overlap) / max(len(tokens), 1)
        scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    results = [
        RetrievedChunk(
            document_id=chunk.document_id,
            filename=chunk.filename,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            score=round(score, 4),
        )
        for score, chunk in scored[:top_k]
    ]
    return SearchResponse(query=query, profile_id=profile_id, results=results)


def _tokenize(text: str) -> list[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return [part for part in cleaned.split() if part]
