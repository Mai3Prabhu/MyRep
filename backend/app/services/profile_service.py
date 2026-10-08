import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Profile
from app.schemas.profile import ProfileCreate, ProfileUpdate


def create_profile(db: Session, data: ProfileCreate) -> Profile:
    """
    Insert a new profile row and return the created ORM object.
    """
    profile = Profile(**data.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)  # Reload the row to pick up DB-generated values (id, timestamps).
    return profile


def get_profile_by_name(db: Session, name: str) -> Profile:
    """
    Fetch the most recently updated profile with this name.
    Matching ignores surrounding spaces and letter case.
    Raises 404 if no profile uses that name.
    """
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name is required.",
        )

    profile = db.scalar(
        select(Profile)
        .where(func.lower(Profile.name) == cleaned.lower())
        .order_by(Profile.updated_at.desc())
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found.",
        )
    return profile


def get_profile(db: Session, profile_id: uuid.UUID) -> Profile:
    """
    Fetch a profile by UUID. Raises 404 if not found.
    """
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found.",
        )
    return profile


def update_profile(db: Session, profile_id: uuid.UUID, data: ProfileUpdate) -> Profile:
    """
    Apply non-null fields from 'data' onto the stored profile, then commit.
    Fields that are None in the request are left unchanged.
    """
    profile = get_profile(db, profile_id)

    # model_dump(exclude_unset=True) returns only the fields the caller actually sent,
    # so we never accidentally overwrite a field with None when it wasn't in the request.
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return profile


def _text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _items(value: object) -> list:
    return value if isinstance(value, list) else []


def _skill_name(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return _text(item.get("name"))
    return ""


def _join_tech(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        names = [_text(part) or _skill_name(part) for part in value]
        return ", ".join(name for name in names if name)
    return ""


def format_saved_profile(profile: Profile) -> str:
    """
    Turn the fields the person typed into the profile form into answerable text.

    Contact preferences are omitted. Uploaded documents are not included.
    """
    lines: list[str] = []
    name = _text(getattr(profile, "name", None))
    if name:
        lines.append(f"Name: {name}")
    headline = _text(getattr(profile, "headline", None))
    if headline:
        lines.append(f"Headline: {headline}")
    about = _text(getattr(profile, "about", None))
    if about:
        lines.append(f"About: {about}")

    skills = [name for item in _items(getattr(profile, "skills", None)) if (name := _skill_name(item))]
    if skills:
        lines.append("Skills: " + ", ".join(skills))

    experience_lines: list[str] = []
    for item in _items(getattr(profile, "experience", None)):
        if not isinstance(item, dict):
            continue
        role = _text(item.get("role"))
        company = _text(item.get("company"))
        start = _text(item.get("start"))
        end = _text(item.get("end"))
        description = _text(item.get("description"))
        title = " at ".join(part for part in (role, company) if part)
        when = "–".join(part for part in (start, end) if part)
        sentence = ", ".join(part for part in (title, when) if part)
        if description:
            sentence = f"{sentence}. {description}" if sentence else description
        if sentence:
            experience_lines.append(f"- {sentence}")
    if experience_lines:
        lines.append("Experience:")
        lines.extend(experience_lines)

    education_lines: list[str] = []
    for item in _items(getattr(profile, "education", None)):
        if not isinstance(item, dict):
            continue
        degree = _text(item.get("degree"))
        institution = _text(item.get("institution"))
        year = _text(item.get("year"))
        sentence = ", ".join(part for part in (degree, institution, year) if part)
        if sentence:
            education_lines.append(f"- {sentence}")
    if education_lines:
        lines.append("Education:")
        lines.extend(education_lines)

    project_lines: list[str] = []
    for item in _items(getattr(profile, "projects", None)):
        if not isinstance(item, dict):
            continue
        project_name = _text(item.get("name"))
        description = _text(item.get("description"))
        tech = _join_tech(item.get("tech"))
        link = _text(item.get("link"))
        sentence = project_name
        if description:
            sentence = f"{sentence}: {description}" if sentence else description
        if tech:
            sentence = f"{sentence} (tech: {tech})" if sentence else f"Tech: {tech}"
        if link:
            sentence = f"{sentence} Link: {link}" if sentence else f"Link: {link}"
        if sentence:
            project_lines.append(f"- {sentence}")
    if project_lines:
        lines.append("Projects:")
        lines.extend(project_lines)

    return "\n".join(lines).strip()


_PROFILE_SECTIONS = ("Name", "Headline", "About", "Skills", "Experience", "Education", "Projects")

_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Education": ("education", "study", "studied", "degree", "college", "university", "school", "graduat"),
    "Projects": ("project", "built", "build", "portfolio"),
    "Experience": ("experience", "work", "worked", "job", "role", "company", "employ"),
    "Skills": ("skill", "technolog", "stack"),
    "About": ("about you", "who are you", "introduce", "yourself", "headline", "background"),
}


def _saved_sections(facts: str) -> dict[str, str]:
    current: str | None = None
    buckets: dict[str, list[str]] = {}
    for raw in facts.splitlines():
        line = raw.strip()
        if not line:
            continue
        matched = False
        for name in _PROFILE_SECTIONS:
            prefix = f"{name}:"
            if line.startswith(prefix):
                current = name
                buckets.setdefault(name, [])
                rest = line[len(prefix):].strip()
                if rest:
                    buckets[name].append(rest)
                matched = True
                break
        if matched or current is None:
            continue
        buckets.setdefault(current, []).append(line[2:].strip() if line.startswith("- ") else line)
    return {name: " ".join(parts).strip() for name, parts in buckets.items() if " ".join(parts).strip()}


def answer_from_saved_profile(question: str, facts: str) -> str | None:
    """
    Answer from the saved form when the language model cannot be called.

    Returns None when the question is not about those fields.
    """
    cleaned = (facts or "").strip()
    if not cleaned:
        return None
    question_l = question.lower()
    sections = _saved_sections(cleaned)
    wanted = [
        name
        for name, keywords in _SECTION_KEYWORDS.items()
        if any(keyword in question_l for keyword in keywords)
    ]
    if any(phrase in question_l for phrase in ("tell me about yourself", "who are you", "your background")):
        wanted = [name for name in ("About", "Experience", "Education", "Projects", "Skills") if name not in wanted] + wanted
    if not wanted:
        return None

    pieces: list[str] = []
    for name in wanted:
        body = sections.get(name, "")
        if not body:
            pieces.append(f"I don't have {name.lower()} saved on this profile yet.")
            continue
        compact = " ".join(body.split())
        if len(compact) > 420:
            compact = compact[:420].rsplit(" ", 1)[0].rstrip(".,;") + "."
        pieces.append(f"{name}: {compact}")
    return " ".join(pieces)


def delete_profile(db: Session, profile_id: uuid.UUID) -> None:
    """
    Delete a profile by UUID. Raises 404 if not found.
    """
    profile = get_profile(db, profile_id)
    db.delete(profile)
    db.commit()
