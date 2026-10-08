import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, String, Text, DateTime, JSON, Uuid, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Profile(Base):
    """
    Represents a user's professional identity in the database.

    Structured columns (name, headline, about) are plain SQL columns because
    they are simple scalar values we might filter or sort by in the future.

    Nested collections (skills, experience, projects, education,
    contact_preferences) are stored as JSON. MySQL's JSON column type stores
    and validates JSON natively (MySQL 5.7.8+). We can always migrate these
    to separate tables later.

    sqlalchemy.Uuid and sqlalchemy.JSON are database-agnostic types —
    SQLAlchemy maps them to the appropriate native type for each engine.
    """

    __tablename__ = "profiles"

    # sqlalchemy.Uuid (capital U, SQLAlchemy 2.x) adapts to each database:
    # on MySQL it stores as CHAR(32) and handles conversion automatically.
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    headline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON columns — MySQL stores and validates these natively.
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    experience: Mapped[list | None] = mapped_column(JSON, nullable=True)
    projects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    education: Mapped[list | None] = mapped_column(JSON, nullable=True)
    contact_preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Layer 4: public visibility flag.
    # Default False — profiles are private until explicitly made public.
    # On MySQL, Boolean maps to TINYINT(1); server_default="0" ensures
    # existing rows get the correct default when this column is added via ALTER.
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # One profile owns many documents. Deleting a profile cascades to its documents.
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="profile", cascade="all, delete-orphan"
    )


class Document(Base):
    """
    Represents a PDF document uploaded by a user and linked to their profile.

    The file itself lives on disk (storage/documents/).
    Only metadata is stored here — the binary PDF is never written to MySQL.

    Future layers will extract text from the file, chunk it, embed it with
    Gemini, and store the vectors in Qdrant. That pipeline reads storage_path
    to locate the original file.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    # Relative path from the backend root, e.g. storage/documents/{profile_id}/{uuid}_name.pdf
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Layer 2.9: indexing status tracking.
    # Default "NOT_INDEXED" is applied both at ORM level (default=) and
    # DB level (server_default=) so that bare ALTER TABLE adds populate correctly.
    indexing_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="NOT_INDEXED",
        server_default="NOT_INDEXED",
    )
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    indexed_chunks: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    # Stores a sanitised user-facing error message when status == FAILED.
    # Internal paths and exception details are logged separately, never stored here.
    indexing_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    profile: Mapped["Profile"] = relationship("Profile", back_populates="documents")


class ContactRequest(Base):
    """
    Layer 5.1 — recorded handoff request from a visitor.

    This is NOT a sent email. Status COMPLETED is reserved for an actual
    delivery integration that does not exist yet. Recording a request
    results in PENDING.
    """

    __tablename__ = "contact_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    visitor_message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
