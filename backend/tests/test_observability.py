"""Layer 8 observability tests. Do not log secrets or full documents."""

from unittest.mock import MagicMock
from uuid import UUID

from app.core.request_context import get_request_id, request_scope
from app.services import agent_service


PROFILE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SECRET = "sk_super_secret_do_not_log"


def test_request_scope_sets_and_resets_id():
    assert get_request_id() == "-"
    with request_scope("abc-123") as rid:
        assert rid == "abc-123"
        assert get_request_id() == "abc-123"
    assert get_request_id() == "-"


def test_handle_question_logs_request_id_not_secrets(monkeypatch, caplog):
    monkeypatch.setattr(
        "app.services.agent_service.profile_service.get_profile",
        lambda db, pid: MagicMock(),
    )
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", SECRET)
    monkeypatch.setattr("app.services.sarvam_service.settings.SARVAM_API_KEY", SECRET)

    def fake_invoke(state, config):
        assert state.get("request_id")
        return {
            "answer": "ok",
            "source_references": [],
            "evidence_status": "no_evidence",
            "intent": "knowledge",
            "query_rewritten": False,
            "retrieval_query": state["question"],
            "retrieved_chunks": [],
        }

    monkeypatch.setattr(
        "app.services.agent_service.get_graph",
        lambda: MagicMock(invoke=fake_invoke),
    )
    with caplog.at_level("INFO"):
        agent_service.handle_question(MagicMock(), PROFILE_ID, "What projects has she built?")
    text = caplog.text
    assert "request_id=" in text
    assert "agent_request_started" in text
    assert "agent_request_finished" in text
    assert SECRET not in text
    assert "sk_super_secret" not in text


def test_finished_log_does_not_include_full_question_or_history(monkeypatch, caplog):
    bulky = "SENSITIVE_HISTORY_BLOB " * 20
    monkeypatch.setattr(
        "app.services.agent_service.profile_service.get_profile",
        lambda db, pid: MagicMock(),
    )
    monkeypatch.setattr(
        "app.services.agent_service.get_graph",
        lambda: MagicMock(
            invoke=lambda state, config: {
                "answer": "ok",
                "source_references": [],
                "evidence_status": "no_evidence",
                "intent": "knowledge",
            }
        ),
    )
    from app.schemas.rag import ConversationTurn

    with caplog.at_level("INFO"):
        agent_service.handle_question(
            MagicMock(),
            PROFILE_ID,
            "short question",
            [ConversationTurn(role="user", content=bulky)],
        )
    assert bulky not in caplog.text
    assert "SENSITIVE_HISTORY_BLOB" not in caplog.text
