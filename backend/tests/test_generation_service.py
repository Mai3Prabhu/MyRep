"""
test_generation_service.py — Unit tests for Layer 2.7 generation service.

All tests mock the Gemini client — no real API key is required.
The mock is patched at google.genai.Client so the service behaves as if the
SDK is present and responding normally.

Tests cover:
  1.  _format_evidence produces correct SOURCE blocks with provenance headers.
  2.  _format_evidence numbers sources starting at 1.
  3.  _format_evidence with a single chunk produces no trailing blank lines.
  4.  generate_answer sends a prompt that includes the question.
  5.  generate_answer sends a prompt that includes all evidence blocks.
  6.  generate_answer uses the model from config.
  7.  generate_answer passes temperature from config.
  8.  generate_answer passes max_output_tokens from config.
  9.  generate_answer includes system instruction in GenerateContentConfig.
  10. generate_answer returns the model's response text.
  11. generate_answer raises HTTP 503 when GEMINI_API_KEY is empty.
  12. generate_answer raises HTTP 503 when GEMINI_API_KEY is whitespace only.
  13. generate_answer raises HTTP 502 when Gemini raises an unexpected exception.
  14. HTTP 502 error message does NOT contain the GEMINI_API_KEY value.
  15. HTTP 503 error message does NOT contain the GEMINI_API_KEY value.
  16. generate_answer works correctly with multiple evidence chunks.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.retrieval import RetrievedChunk
from app.services import generation_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PROFILE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SAMPLE_DOC_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
REAL_API_KEY = "SUPER_SECRET_KEY_DO_NOT_LOG"


def make_chunk(
    chunk_index: int = 0,
    page_number: int = 1,
    filename: str = "resume.pdf",
    text: str = "Worked on distributed systems projects.",
    score: float = 0.95,
    doc_id: uuid.UUID = SAMPLE_DOC_ID,
) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=doc_id,
        filename=filename,
        page_number=page_number,
        chunk_index=chunk_index,
        text=text,
        score=score,
    )


def make_gemini_client_mock(answer: str = "This is a grounded answer.") -> MagicMock:
    """Return a Gemini client mock whose generate_content returns the given answer."""
    response = MagicMock()
    response.text = answer
    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


# ---------------------------------------------------------------------------
# 1–3. _format_evidence — evidence block formatting
# ---------------------------------------------------------------------------

def test_format_evidence_contains_source_header():
    chunk = make_chunk(chunk_index=3, page_number=2, filename="projects.pdf")
    result = generation_service._format_evidence([chunk])
    assert "--- SOURCE 1 ---" in result


def test_format_evidence_includes_provenance_fields():
    chunk = make_chunk(chunk_index=3, page_number=2, filename="projects.pdf")
    result = generation_service._format_evidence([chunk])
    assert "projects.pdf" in result
    assert "Page: 2" in result
    assert "Chunk: 3" in result


def test_format_evidence_includes_chunk_text():
    chunk = make_chunk(text="Led a team of five engineers.")
    result = generation_service._format_evidence([chunk])
    assert "Led a team of five engineers." in result


def test_format_evidence_numbers_sources_from_one():
    chunks = [make_chunk(chunk_index=i) for i in range(3)]
    result = generation_service._format_evidence(chunks)
    assert "--- SOURCE 1 ---" in result
    assert "--- SOURCE 2 ---" in result
    assert "--- SOURCE 3 ---" in result


def test_format_evidence_no_source_4_for_three_chunks():
    chunks = [make_chunk(chunk_index=i) for i in range(3)]
    result = generation_service._format_evidence(chunks)
    assert "--- SOURCE 4 ---" not in result


def test_format_evidence_single_chunk_no_trailing_separator():
    chunk = make_chunk()
    result = generation_service._format_evidence([chunk])
    # No double-newline separator at end (no trailing '\n\n')
    assert not result.endswith("\n\n")


# ---------------------------------------------------------------------------
# 4–10. generate_answer — prompt content, model/config, return value
# ---------------------------------------------------------------------------

def test_generate_answer_includes_question_in_prompt(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("What ML frameworks has this person used?", [make_chunk()])

    call_kwargs = client_mock.models.generate_content.call_args.kwargs
    prompt = call_kwargs["contents"]
    assert "What ML frameworks has this person used?" in prompt


def test_generate_answer_includes_evidence_in_prompt(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    chunk = make_chunk(text="Implemented transformer models using PyTorch.")
    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("What did they build?", [chunk])

    call_kwargs = client_mock.models.generate_content.call_args.kwargs
    prompt = call_kwargs["contents"]
    assert "Implemented transformer models using PyTorch." in prompt
    assert "--- SOURCE 1 ---" in prompt


def test_generate_answer_uses_model_from_config(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-pro")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("question", [make_chunk()])

    call_kwargs = client_mock.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-pro"


def test_generate_answer_passes_temperature_from_config(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.42)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("question", [make_chunk()])

    config_arg = client_mock.models.generate_content.call_args.kwargs["config"]
    assert config_arg.temperature == pytest.approx(0.42)


def test_generate_answer_passes_max_tokens_from_config(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 2048)

    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("question", [make_chunk()])

    config_arg = client_mock.models.generate_content.call_args.kwargs["config"]
    assert config_arg.max_output_tokens == 2048


def test_generate_answer_includes_system_instruction(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("question", [make_chunk()])

    config_arg = client_mock.models.generate_content.call_args.kwargs["config"]
    assert config_arg.system_instruction is not None
    # The system instruction must contain grounding language
    assert "evidence" in config_arg.system_instruction.lower() or "materials" in config_arg.system_instruction.lower()


def test_generate_answer_system_instruction_contains_data_boundary(monkeypatch):
    """The system instruction must explicitly mark retrieved content as untrusted data."""
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("question", [make_chunk()])

    config_arg = client_mock.models.generate_content.call_args.kwargs["config"]
    instr = config_arg.system_instruction.lower()
    assert "untrusted" in instr or "data" in instr
    assert "instruction" in instr or "instructions" in instr


def test_generate_answer_system_instruction_handles_conflicting_evidence(monkeypatch):
    """The system instruction must address conflicting evidence handling."""
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("question", [make_chunk()])

    config_arg = client_mock.models.generate_content.call_args.kwargs["config"]
    instr = config_arg.system_instruction.lower()
    assert "conflict" in instr or "contradict" in instr or "inconsisten" in instr


def test_generate_answer_returns_model_response_text(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = make_gemini_client_mock(answer="They built a recommendation engine.")

    with patch("google.genai.Client", return_value=client_mock):
        result = generation_service.generate_answer("What did they build?", [make_chunk()])

    assert result == "They built a recommendation engine."


def test_generate_answer_with_multiple_chunks(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    chunks = [
        make_chunk(chunk_index=0, text="First chunk content."),
        make_chunk(chunk_index=1, text="Second chunk content."),
        make_chunk(chunk_index=2, text="Third chunk content."),
    ]
    client_mock = make_gemini_client_mock(answer="Multi-source answer.")

    with patch("google.genai.Client", return_value=client_mock):
        result = generation_service.generate_answer("question", chunks)

    call_kwargs = client_mock.models.generate_content.call_args.kwargs
    prompt = call_kwargs["contents"]
    assert "--- SOURCE 1 ---" in prompt
    assert "--- SOURCE 2 ---" in prompt
    assert "--- SOURCE 3 ---" in prompt
    assert "First chunk content." in prompt
    assert "Second chunk content." in prompt
    assert "Third chunk content." in prompt
    assert result == "Multi-source answer."


# ---------------------------------------------------------------------------
# 11–15. Error handling — credential missing, API failure, no key leakage
# ---------------------------------------------------------------------------

def test_generate_answer_raises_503_when_key_empty(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "")

    with pytest.raises(HTTPException) as exc_info:
        generation_service.generate_answer("question", [make_chunk()])

    assert exc_info.value.status_code == 503


def test_generate_answer_raises_503_when_key_whitespace(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "   ")

    with pytest.raises(HTTPException) as exc_info:
        generation_service.generate_answer("question", [make_chunk()])

    assert exc_info.value.status_code == 503


def test_generate_answer_raises_502_on_gemini_failure(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = MagicMock()
    client_mock.models.generate_content.side_effect = RuntimeError("quota exceeded")

    with patch("google.genai.Client", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            generation_service.generate_answer("question", [make_chunk()])

    assert exc_info.value.status_code == 502
    assert "quota exceeded" in exc_info.value.detail


def test_generate_answer_502_does_not_leak_api_key(monkeypatch):
    """The HTTP 502 error detail must never contain the Gemini API key."""
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", REAL_API_KEY)
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = MagicMock()
    client_mock.models.generate_content.side_effect = RuntimeError("network error")

    with patch("google.genai.Client", return_value=client_mock):
        with pytest.raises(HTTPException) as exc_info:
            generation_service.generate_answer("question", [make_chunk()])

    assert REAL_API_KEY not in exc_info.value.detail


def test_generate_answer_503_does_not_leak_api_key(monkeypatch):
    """The HTTP 503 error detail must never contain the Gemini API key."""
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "")

    with pytest.raises(HTTPException) as exc_info:
        generation_service.generate_answer("question", [make_chunk()])

    assert REAL_API_KEY not in exc_info.value.detail


# ---------------------------------------------------------------------------
# Layer 3.6 — Conversation context in generation prompt
# ---------------------------------------------------------------------------

from app.schemas.rag import ConversationTurn


def test_generate_answer_includes_conversation_context_when_provided(monkeypatch):
    """When conversation_history is supplied, the prompt must contain the context block."""
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    history = [
        ConversationTurn(role="user", content="Tell me about MindMate."),
        ConversationTurn(role="assistant", content="MindMate is a mental health application."),
    ]
    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("Why did she use FastAPI?", [make_chunk()], history)

    prompt = client_mock.models.generate_content.call_args.kwargs["contents"]
    assert "MindMate is a mental health application." in prompt
    assert "CONVERSATION CONTEXT" in prompt


def test_generate_answer_context_labelled_not_authoritative(monkeypatch):
    """The conversation context block must be labelled as reference only, not evidence."""
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    history = [ConversationTurn(role="user", content="Previous question.")]
    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("Follow-up?", [make_chunk()], history)

    prompt = client_mock.models.generate_content.call_args.kwargs["contents"]
    prompt_lower = prompt.lower()
    # Prompt must indicate history is for reference / not authoritative evidence
    assert "reference" in prompt_lower or "not authoritative" in prompt_lower or "contextual" in prompt_lower


def test_generate_answer_without_history_has_no_context_block(monkeypatch):
    """Without history, the prompt must NOT contain a CONVERSATION CONTEXT section."""
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("question", [make_chunk()])

    prompt = client_mock.models.generate_content.call_args.kwargs["contents"]
    assert "CONVERSATION CONTEXT" not in prompt


def test_generate_answer_system_instruction_marks_history_as_untrusted(monkeypatch):
    """System instruction must address conversation context as untrusted user input."""
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("question", [make_chunk()])

    config_arg = client_mock.models.generate_content.call_args.kwargs["config"]
    instr = config_arg.system_instruction.lower()
    # System instruction must address that conversation history is not authoritative
    assert "conversation" in instr or "history" in instr or "context" in instr


def test_generate_answer_voice_channel_adds_spoken_style_without_changing_system(monkeypatch):
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("app.services.generation_service.settings.GEMINI_GENERATION_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_TEMPERATURE", 0.1)
    monkeypatch.setattr("app.services.generation_service.settings.GENERATION_MAX_TOKENS", 512)

    client_mock = make_gemini_client_mock()

    with patch("google.genai.Client", return_value=client_mock):
        generation_service.generate_answer("question", [make_chunk()], channel="voice")

    prompt = client_mock.models.generate_content.call_args.kwargs["contents"]
    config_arg = client_mock.models.generate_content.call_args.kwargs["config"]
    assert "VOICE CHANNEL" in prompt
    assert "Never invent" in config_arg.system_instruction or "never invent" in config_arg.system_instruction.lower()
