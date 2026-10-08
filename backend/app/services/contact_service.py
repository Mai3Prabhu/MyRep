"""
contact_service.py — Layer 5.1 controlled contact / handoff.

Permission model (smallest safe contract):

    contact_preferences is unstructured JSON. The only shareable methods are
    keys inside an explicit nested object:

        { "public": { "email": "...", "linkedin": "...", "website": "..." } }

    Any other key (email, phone, preferred, allow_inquiries, etc.) is private
    and is NEVER returned to visitors or to the LLM as contact information.

No email/CRM delivery exists. create_contact_request records PENDING only.
COMPLETED is reserved for a future delivery integration.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import ContactRequest
from app.services import profile_service

logger = logging.getLogger(__name__)

_ALLOWED_PUBLIC_KEYS = ("email", "linkedin", "website")

_CONFIRM_RE = re.compile(
    r"\b(yes|yeah|yep|please do|please record|go ahead|confirm|"
    r"leave a message|record (a |this )?request|send (a |the )?request|"
    r"i('d| would) like you to (record|send|pass))\b",
    re.IGNORECASE,
)


def extract_public_contact_methods(prefs: dict[str, Any] | None) -> dict[str, str]:
    """
    Return only owner-declared public contact methods.

    Empty dict means no public method exists — never a fallback to private keys.
    """
    if not isinstance(prefs, dict):
        return {}
    public = prefs.get("public")
    if not isinstance(public, dict):
        return {}
    methods: dict[str, str] = {}
    for key in _ALLOWED_PUBLIC_KEYS:
        value = public.get(key)
        if isinstance(value, str) and value.strip():
            methods[key] = value.strip()
    return methods


def visitor_confirmed_contact(question: str, conversation_history: list | None) -> bool:
    """
    Deterministic confirmation check. The LLM does not decide to execute.

    Confirmation is true when the current question clearly asks to record/send
    a request, or is a short affirmative after MyRep offered to record one.
    """
    text = (question or "").strip()
    if not text:
        return False
    if _CONFIRM_RE.search(text):
        return True
    if conversation_history:
        last_assistant = ""
        for turn in reversed(conversation_history):
            role = turn.role if hasattr(turn, "role") else turn.get("role")
            content = turn.content if hasattr(turn, "content") else turn.get("content", "")
            if role == "assistant":
                last_assistant = content.lower()
                break
        short_yes = text.lower() in {"yes", "yeah", "yep", "please", "ok", "okay", "sure"}
        offered = "contact request" in last_assistant or "record" in last_assistant
        if short_yes and offered:
            return True
    return False


def create_contact_request(
    db: Session,
    profile_id: uuid.UUID,
    visitor_message: str,
) -> dict[str, str]:
    """
    Persist a PENDING handoff. Does not send email.

    profile_id must come from the authorized API path, never from the model.
    Returns a plain dict with status PENDING or FAILED.
    """
    message = (visitor_message or "").strip()
    if not message:
        return {"status": "FAILED", "detail": "empty_message"}

    profile_service.get_profile(db, profile_id)

    try:
        row = ContactRequest(
            profile_id=profile_id,
            visitor_message=message[:4000],
            status="PENDING",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(
            "contact_action_completed profile_id=%s request_id=%s status=PENDING",
            profile_id,
            row.id,
        )
        return {"status": "PENDING", "request_id": str(row.id)}
    except Exception:
        db.rollback()
        logger.error("contact_action_failed profile_id=%s", profile_id)
        return {"status": "FAILED", "detail": "persist_error"}


def format_contact_answer(
    profile_name: str,
    public_methods: dict[str, str],
    confirmed: bool,
    action: dict[str, str] | None,
    spoken: bool = False,
) -> tuple[str, str]:
    """
    Build the visitor-facing contact reply.

    Returns (answer, contact_status) where contact_status is one of:
    none | offered | pending | failed
    """
    if not public_methods:
        return (
            f"{profile_name} hasn't provided a public contact method.",
            "none",
        )

    if spoken:
        listed = "; ".join(f"{key} {value}" for key, value in public_methods.items())
        if confirmed and action:
            if action.get("status") == "PENDING":
                return (
                    f"You can reach {profile_name} at {listed}. "
                    "I've recorded the contact request as pending. "
                    "It hasn't been emailed or delivered yet.",
                    "pending",
                )
            return (
                f"You can reach {profile_name} at {listed}. "
                "I couldn't record that contact request. Please try again later.",
                "failed",
            )
        return (
            f"You can reach {profile_name} at {listed}. "
            "Would you like me to record a contact request? "
            "I will not send a message unless you confirm.",
            "offered",
        )

    lines = [f"You can reach {profile_name} through these public channels:"]
    for key, value in public_methods.items():
        lines.append(f"- {key}: {value}")

    if confirmed and action:
        if action.get("status") == "PENDING":
            lines.append(
                "I've recorded a contact request for them. "
                "This has been saved as pending — it has not been emailed or delivered."
            )
            return "\n".join(lines), "pending"
        lines.append(
            "I couldn't record that contact request. Please try again later."
        )
        return "\n".join(lines), "failed"

    lines.append(
        "Would you like me to record a contact request for them? "
        "I will not send a message unless you confirm."
    )
    return "\n".join(lines), "offered"
