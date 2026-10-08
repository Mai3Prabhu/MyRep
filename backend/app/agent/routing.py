"""Conditional edges. Routing only — never treats intent as a professional fact."""

from app.agent.state import AgentState
from app.services.evidence_service import EvidenceState


def after_intent(state: AgentState) -> str:
    intent = state.get("intent") or "knowledge"
    if intent == "contact":
        return "route_contact"
    if intent == "unsupported":
        return "handle_unsupported"
    return "rewrite_query"


def after_evidence(state: AgentState) -> str:
    status = state.get("evidence_status")
    if status == EvidenceState.EVIDENCE_AVAILABLE.value:
        return "generate_answer"
    return "clarify"
