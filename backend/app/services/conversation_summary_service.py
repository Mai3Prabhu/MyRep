"""
conversation_summary_service.py — deterministic per-turn conversation digest.

The frontend merges one digest per turn into a session-level
"What we've discussed" view. This module:

  - makes NO model call (works when generation is unavailable or quota-limited)
  - never persists anything
  - is never fed back into retrieval or generation

Grounded by construction:
  - topics come from a fixed taxonomy matched against the visitor's question
  - entities and technologies are terms from an allowed vocabulary
    (public-safe profile fields + a fixed technology lexicon) that literally
    appear in an affirmative sentence of the Rep's answer
  - key points are sentences quoted from the Rep's own answer
  - an "I don't have enough information" answer contributes no entities,
    technologies, or key points

The summary is therefore a view of what was said, not a source of truth.
Profile data, approved documents, and RAG evidence remain authoritative.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.schemas.rag import TurnSummary

_MAX_QUESTION_CHARS = 90
_MAX_KEY_POINT_CHARS = 140
_MAX_TERMS = 6

# Ordered: the first matching topics win when a question touches several.
_TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Projects", ("project", "built", "build", "portfolio", "worked on", "made", "created")),
    ("Experience", ("experience", "work at", "worked at", "job", "role", "company", "intern", "employ")),
    ("Skills", ("skill", "technolog", "stack", "know", "tools", "language", "framework", "proficien")),
    ("Education", ("education", "degree", "study", "studied", "college", "university", "school", "graduat")),
    ("Architecture", ("backend", "frontend", "api", "server", "database", "architecture", "deploy", "infrastructure", "design")),
    ("AI & ML", ("machine learning", " ml", " ai", "llm", "rag", "embedding", "model", "neural", "nlp")),
    ("Background", ("about her", "about him", "about them", "background", "who is", "introduce", "yourself", "tell me about")),
)

# Well-known technology names. Recognition only: a name is listed for a turn
# solely because the Rep's own answer used it.
_TECH_LEXICON: tuple[str, ...] = (
    "Python", "Java", "JavaScript", "TypeScript", "Golang", "Rust", "C++", "C#", "Kotlin", "Swift", "Dart", "SQL",
    "React", "Next.js", "Node.js", "Vue", "Angular", "Svelte", "Tailwind", "Flutter",
    "FastAPI", "Flask", "Django", "Express", "Spring", "GraphQL", "REST",
    "PyTorch", "TensorFlow", "Keras", "scikit-learn", "Pandas", "NumPy", "OpenCV", "Hugging Face",
    "Transformers", "BERT", "LangChain", "LangGraph", "LlamaIndex", "OpenAI", "Gemini", "Whisper",
    "Streamlit", "Gradio", "Sarvam",
    "MySQL", "PostgreSQL", "SQLite", "MongoDB", "Redis", "Qdrant", "Pinecone", "Elasticsearch",
    "Firebase", "Supabase", "SQLAlchemy",
    "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Vercel", "Terraform", "Jenkins", "GitHub Actions",
    "Kafka", "RabbitMQ", "Celery", "Spark", "Airflow", "Linux", "Git",
)

_INSUFFICIENT_MARKERS = (
    "don't have enough information",
    "do not have enough information",
    "not enough information",
)

# A sentence with one of these talks about something that is NOT documented,
# so its terms must not appear as "discussed" facts.
_NEGATION_MARKERS = (
    "no information",
    "not mentioned",
    "not documented",
    "not covered",
    "no mention",
    "don't have",
    "do not have",
    "doesn't mention",
    "does not mention",
    "isn't mentioned",
    "is not mentioned",
    "not in the",
    "unable to confirm",
    "can't confirm",
    "cannot confirm",
)

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_MARKDOWN_RE = re.compile(r"[*_`#>]+")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)


def is_insufficient_answer(answer: str) -> bool:
    """True when the answer's opening says the profile cannot support it."""
    first = _sentences(answer)[:1]
    if not first:
        return False
    lowered = first[0].lower().replace("’", "'")
    return any(marker in lowered for marker in _INSUFFICIENT_MARKERS)


def build_vocabulary(
    *,
    projects: object = None,
    experience: object = None,
    education: object = None,
    skills: object = None,
) -> tuple[list[str], list[str]]:
    """
    Return (entity_names, technology_names) from public-safe profile fields.

    Only names are read. contact_preferences, documents, and free-text
    descriptions are never part of the vocabulary.
    """
    entities: list[str] = []
    technologies: list[str] = []
    for item in _items(projects):
        if isinstance(item, dict):
            entities.append(_text(item.get("name")))
            technologies.extend(_names(item.get("tech")))
    for item in _items(experience):
        if isinstance(item, dict):
            entities.append(_text(item.get("company")))
    for item in _items(education):
        if isinstance(item, dict):
            entities.append(_text(item.get("institution")))
    technologies.extend(_names(skills))
    return _unique(e for e in entities if e), _unique(t for t in technologies if t)


def build_turn_summary(
    *,
    question: str,
    answer: str,
    intent: str | None,
    evidence_status: str | None,
    entity_vocabulary: Iterable[str] = (),
    technology_vocabulary: Iterable[str] = (),
    exclude: Iterable[str] = (),
) -> TurnSummary:
    """Digest one completed turn. Pure function; no I/O."""
    outcome = _outcome(answer, intent, evidence_status)
    topics = ["Contact"] if intent == "contact" else _topics(question)

    entities: list[str] = []
    technologies: list[str] = []
    key_points: list[str] = []
    if outcome == "answered":
        affirmative = [s for s in _sentences(answer) if not _is_negated(s)]
        excluded = {e.strip().lower() for e in exclude if e and e.strip()}
        technologies = _matches(
            affirmative, _unique([*technology_vocabulary, *_TECH_LEXICON]), excluded
        )
        tech_keys = {t.lower() for t in technologies}
        entities = [
            e
            for e in _matches(affirmative, list(entity_vocabulary), excluded)
            if e.lower() not in tech_keys
        ]
        if affirmative:
            key_points = [_clip(affirmative[0], _MAX_KEY_POINT_CHARS)]

    return TurnSummary(
        question=_clip(" ".join((question or "").split()), _MAX_QUESTION_CHARS),
        topics=topics,
        entities=entities[:_MAX_TERMS],
        technologies=technologies[:_MAX_TERMS],
        key_points=key_points,
        outcome=outcome,
    )


# ── helpers ─────────────────────────────────────────────────────────────────


def _outcome(answer: str, intent: str | None, evidence_status: str | None) -> str:
    if intent == "contact":
        return "contact"
    if intent == "unsupported":
        return "declined"
    if evidence_status != "evidence_available" or is_insufficient_answer(answer):
        return "not_in_profile"
    return "answered"


def _topics(question: str) -> list[str]:
    text = f" {(question or '').lower()} "
    found = [topic for topic, keys in _TOPIC_RULES if any(k in text for k in keys)]
    return found[:2] or ["General"]


def _sentences(text: str) -> list[str]:
    plain = _BULLET_RE.sub("", text or "")
    plain = _MARKDOWN_RE.sub("", plain)
    parts: list[str] = []
    for line in plain.splitlines():
        line = " ".join(line.split())
        if line:
            parts.extend(p.strip() for p in _SENTENCE_RE.split(line) if p.strip())
    return parts


def _is_negated(sentence: str) -> bool:
    lowered = sentence.lower().replace("’", "'")
    return any(marker in lowered for marker in _NEGATION_MARKERS)


def _term_pattern(term: str) -> re.Pattern:
    # "REST", "Spring", "Python" are also ordinary words or acronyms, so they
    # must match exactly. Mixed-case names ("FastAPI", "Next.js") match any case.
    plain_word = term.isalpha() and (term.isupper() or term == term.capitalize())
    flags = 0 if plain_word else re.IGNORECASE
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", flags)


def _matches(sentences: list[str], vocabulary: list[str], excluded: set[str]) -> list[str]:
    body = "\n".join(sentences)
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    for term in vocabulary:
        key = term.lower()
        if len(term) < 2 or key in seen or key in excluded:
            continue
        match = _term_pattern(term).search(body)
        if match:
            seen.add(key)
            found.append((match.start(), term))
    # Order of first mention reads naturally in the UI.
    return [term for _, term in sorted(found)]


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _items(value: object) -> list:
    return value if isinstance(value, list) else []


def _names(value: object) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    names: list[str] = []
    for item in _items(value):
        if isinstance(item, str):
            names.append(item.strip())
        elif isinstance(item, dict):
            names.append(_text(item.get("name")))
    return [n for n in names if n]


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out
