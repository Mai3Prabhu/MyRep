"""
Lightweight startup migrations for MyRep (MVP alternative to Alembic).

Fresh installs get all columns via create_all. Existing installs get new
columns added here on the next server start. Each migration is idempotent.
"""
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Layer 2.9 — Indexing status columns added to the documents table.
_DOCUMENT_STATUS_COLUMNS: list[tuple[str, str]] = [
    ("indexing_status", "VARCHAR(20) NOT NULL DEFAULT 'NOT_INDEXED'"),
    ("indexed_at", "DATETIME NULL"),
    ("indexed_chunks", "INT NULL"),
    ("indexing_error", "TEXT NULL"),
]

_PROFILE_VISIBILITY_COLUMNS: list[tuple[str, str]] = [
    ("is_public", "TINYINT(1) NOT NULL DEFAULT 0"),
]


def _column_exists(conn, table: str, column: str) -> bool:
    """Return True if *column* already exists in *table* (current schema)."""
    count = conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = :table "
            "AND column_name = :col"
        ),
        {"table": table, "col": column},
    ).scalar()
    return bool(count)


def ensure_document_status_columns(engine: Engine) -> None:
    """
    Add Layer 2.9 indexing status columns to the documents table if absent.

    Runs at every server start. Columns that already exist are skipped.
    On a fresh install, create_all creates all columns first so this is a no-op.
    """
    with engine.connect() as conn:
        for col_name, col_def in _DOCUMENT_STATUS_COLUMNS:
            if not _column_exists(conn, "documents", col_name):
                logger.info("migration: adding column documents.%s", col_name)
                conn.execute(
                    text(f"ALTER TABLE documents ADD COLUMN {col_name} {col_def}")
                )
                conn.commit()


def ensure_profile_visibility_column(engine: Engine) -> None:
    """
    Add Layer 4 is_public column to the profiles table if absent.

    Default is 0 (False) so existing profiles remain private on upgrade.
    """
    with engine.connect() as conn:
        for col_name, col_def in _PROFILE_VISIBILITY_COLUMNS:
            if not _column_exists(conn, "profiles", col_name):
                logger.info("migration: adding column profiles.%s", col_name)
                conn.execute(
                    text(f"ALTER TABLE profiles ADD COLUMN {col_name} {col_def}")
                )
                conn.commit()
