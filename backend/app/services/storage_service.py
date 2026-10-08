"""
storage_service.py — local file persistence for uploaded documents.

All file I/O is isolated here so that replacing local disk storage with
S3, GCS, or another provider in a later layer only requires changing this
module. The rest of the application works with opaque storage paths.
"""

import re
import uuid
from pathlib import Path

from app.core.config import settings


def _sanitize_filename(original: str) -> str:
    """
    Derive a safe filename stem from the original upload name.

    - Strips the extension (we always write .pdf ourselves)
    - Replaces anything that is not a word character or hyphen with an underscore
    - Caps length at 100 characters to avoid filesystem limits
    """
    stem = Path(original).stem
    safe = re.sub(r"[^\w\-]", "_", stem)
    return safe[:100] or "document"


def _storage_root() -> Path:
    """Return the base storage directory, creating it if it does not exist."""
    root = Path(settings.DOCUMENT_STORAGE_PATH)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_file(profile_id: uuid.UUID, original_filename: str, content: bytes) -> str:
    """
    Write PDF content to disk under a profile-scoped subdirectory.

    The stored filename is:  {random_hex}_{safe_stem}.pdf
    This avoids collisions and prevents path traversal — the caller-supplied
    name is only used for the human-readable stem, never as the actual path.

    Returns a path relative to the backend root (e.g.
    'storage/documents/{profile_id}/{hex}_name.pdf') that is safe to store
    in MySQL and reconstruct later.
    """
    profile_dir = _storage_root() / str(profile_id)
    profile_dir.mkdir(parents=True, exist_ok=True)

    safe_stem = _sanitize_filename(original_filename)
    stored_name = f"{uuid.uuid4().hex}_{safe_stem}.pdf"
    file_path = profile_dir / stored_name

    file_path.write_bytes(content)

    # Return a portable relative path so the stored value is not machine-specific.
    return f"{settings.DOCUMENT_STORAGE_PATH}/{profile_id}/{stored_name}"


def delete_file(storage_path: str) -> None:
    """
    Remove a file from disk given its stored relative path.
    Silently ignores missing files (idempotent).
    """
    path = Path(storage_path)
    if path.exists():
        path.unlink()


def get_file_path(storage_path: str) -> Path:
    """
    Convert a stored relative storage_path string into a Path object.

    The path is relative to the backend root (the directory from which uvicorn
    is run). It is always derived from a trusted Document record — never from
    client-supplied input — so path traversal is not a concern here.

    Does not verify existence; callers should check path.exists() when needed.
    """
    return Path(storage_path)
