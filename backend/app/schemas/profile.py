import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas (what the API accepts)
# ---------------------------------------------------------------------------

class ProfileCreate(BaseModel):
    """
    Schema for POST /profiles — creating a new profile.
    Only 'name' is required. Everything else is optional at creation time.
    """

    name: str = Field(..., min_length=1, max_length=255)
    headline: str | None = Field(None, max_length=500)
    about: str | None = None

    skills: list[Any] | None = None
    experience: list[Any] | None = None
    projects: list[Any] | None = None
    education: list[Any] | None = None
    contact_preferences: dict[str, Any] | None = None


class ProfileUpdate(BaseModel):
    """
    Schema for PUT /profiles/{id} — replacing/updating a profile.
    All fields are optional so callers can send only what changed.
    This is a partial update pattern; every field present will overwrite the stored value.
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    headline: str | None = Field(None, max_length=500)
    about: str | None = None

    skills: list[Any] | None = None
    experience: list[Any] | None = None
    projects: list[Any] | None = None
    education: list[Any] | None = None
    contact_preferences: dict[str, Any] | None = None
    # Layer 4: MVP public-share flag. Default remains false unless the owner
    # explicitly sends this field. Not included on ProfileCreate so new
    # profiles stay private.
    is_public: bool | None = None


# ---------------------------------------------------------------------------
# Response schema (what the API returns)
# ---------------------------------------------------------------------------

class ProfileResponse(BaseModel):
    """
    Schema for API responses. We never return the raw SQLAlchemy model directly —
    this schema controls exactly what the caller sees, and enforces type safety.
    """

    id: uuid.UUID
    name: str
    headline: str | None
    about: str | None

    skills: list[Any] | None
    experience: list[Any] | None
    projects: list[Any] | None
    education: list[Any] | None
    contact_preferences: dict[str, Any] | None
    is_public: bool = False

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
    # from_attributes=True lets Pydantic read values from SQLAlchemy ORM objects,
    # not just plain dicts.
