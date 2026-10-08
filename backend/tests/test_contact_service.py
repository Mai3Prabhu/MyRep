"""Tests for Layer 5.1 contact permission model and PENDING handoff records."""

import uuid
from unittest.mock import MagicMock

from app.services import contact_service


def test_extract_public_methods_from_nested_public_object():
    prefs = {
        "email": "private@example.com",
        "phone": "555-0100",
        "public": {
            "email": "public@example.com",
            "linkedin": "https://linkedin.com/in/example",
        },
    }
    methods = contact_service.extract_public_contact_methods(prefs)
    assert methods == {
        "email": "public@example.com",
        "linkedin": "https://linkedin.com/in/example",
    }
    assert "phone" not in methods
    assert "private@example.com" not in methods.values()


def test_extract_public_methods_empty_when_no_public_key():
    prefs = {"preferred": "email", "allow_inquiries": True, "email": "secret@example.com"}
    assert contact_service.extract_public_contact_methods(prefs) == {}


def test_extract_public_methods_none_prefs():
    assert contact_service.extract_public_contact_methods(None) == {}


def test_private_keys_never_exposed_as_public():
    methods = contact_service.extract_public_contact_methods(
        {"phone": "555-0100", "email": "hidden@example.com"}
    )
    assert methods == {}


def test_format_contact_answer_none_when_no_public_method():
    answer, status = contact_service.format_contact_answer(
        "Maitri", {}, confirmed=False, action=None
    )
    assert "hasn't provided a public contact method" in answer
    assert "555" not in answer
    assert status == "none"


def test_format_contact_answer_offers_only_public_methods():
    answer, status = contact_service.format_contact_answer(
        "Maitri",
        {"email": "public@example.com"},
        confirmed=False,
        action=None,
    )
    assert "public@example.com" in answer
    assert "confirm" in answer.lower()
    assert status == "offered"


def test_format_contact_answer_pending_does_not_claim_delivery():
    answer, status = contact_service.format_contact_answer(
        "Maitri",
        {"email": "public@example.com"},
        confirmed=True,
        action={"status": "PENDING"},
    )
    assert status == "pending"
    assert "pending" in answer.lower()
    assert "not been emailed" in answer.lower() or "not been emailed" in answer


def test_format_contact_answer_failed():
    answer, status = contact_service.format_contact_answer(
        "Maitri",
        {"email": "public@example.com"},
        confirmed=True,
        action={"status": "FAILED"},
    )
    assert status == "failed"
    assert "couldn't record" in answer.lower()


def test_visitor_confirmed_contact_from_phrase():
    assert contact_service.visitor_confirmed_contact(
        "Please record a contact request. I'm hiring for a RAG role.",
        None,
    )


def test_visitor_not_confirmed_on_first_contact_question():
    assert not contact_service.visitor_confirmed_contact(
        "How can I contact her?",
        None,
    )


def test_create_contact_request_empty_message_failed():
    db = MagicMock()
    result = contact_service.create_contact_request(
        db, uuid.uuid4(), "   "
    )
    assert result["status"] == "FAILED"
    db.add.assert_not_called()


def test_create_contact_request_records_pending_not_completed(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr("app.services.profile_service.get_profile", lambda db, pid: MagicMock())

    result = contact_service.create_contact_request(
        db, uuid.uuid4(), "I'd like to discuss a role."
    )

    assert result["status"] == "PENDING"
    assert result["status"] != "COMPLETED"
    db.add.assert_called_once()
    db.commit.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.status == "PENDING"
    assert added.visitor_message == "I'd like to discuss a role."


def test_format_contact_answer_spoken_pending_does_not_claim_email():
    answer, status = contact_service.format_contact_answer(
        "Maitri",
        {"linkedin": "https://linkedin.com/in/maitri"},
        confirmed=True,
        action={"status": "PENDING"},
        spoken=True,
    )
    assert status == "pending"
    assert "linkedin.com/in/maitri" in answer
    assert "pending" in answer.lower()
    assert "emailed" in answer.lower() or "delivered" in answer.lower()
    assert "I've emailed" not in answer
