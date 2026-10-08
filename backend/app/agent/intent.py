"""
Intent classification: routing, not truth.

Rules handle obvious CONTACT / UNSUPPORTED cases without an LLM call.
Ambiguous questions fall through to LangChain structured classification,
then default to KNOWLEDGE so professional questions are not dropped.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import settings
from app.agent.state import Intent

logger = logging.getLogger(__name__)

IntentName = Literal["knowledge", "contact", "unsupported"]


class ClassifiedIntent(BaseModel):
    """LangChain structured-output schema. Classification is routing only."""

    intent: IntentName = Field(
        description="knowledge = professional background questions; "
        "contact = visitor wants to get in touch; "
        "unsupported = salary, negotiation, guarantees, private data, unrelated"
    )


_CONTACT_RE = re.compile(
    r"\b(contact|get in touch|reach (her|him|them)|email|linkedin|"
    r"work with|hire|hiring|discuss (a |this )?project|interview|"
    r"available for|availability)\b",
    re.IGNORECASE,
)

_UNSUPPORTED_RE = re.compile(
    r"\b(salary|compensation|negotiate|negotiation|guarantee|"
    r"accept (this |the )?(offer|contract|project)|sign (a )?contract|"
    r"private (phone|number|address)|home address|"
    r"social security|password)\b",
    re.IGNORECASE,
)


def classify_with_rules(question: str) -> Intent | None:
    text = (question or "").strip()
    if not text:
        return "unsupported"
    if _UNSUPPORTED_RE.search(text):
        return "unsupported"
    if _CONTACT_RE.search(text):
        return "contact"
    return None


def classify_with_llm(question: str) -> Intent | None:
    """LangChain structured intent classification. Returns None on failure."""
    key = (settings.GEMINI_API_KEY or "").strip()
    if not key:
        return None
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_GENERATION_MODEL,
            google_api_key=key,
            temperature=0,
            max_retries=0,
        )
        structured = llm.with_structured_output(ClassifiedIntent)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Classify the visitor message for an AI professional representative. "
                    "knowledge = questions about experience, projects, skills, education. "
                    "contact = wanting to get in touch, hire, or leave a message. "
                    "unsupported = salary, negotiation, guarantees, private phone/address, "
                    "or unrelated topics. Classification is routing only — not a factual claim.",
                ),
                ("human", "{question}"),
            ]
        )
        result = (prompt | structured).invoke({"question": question[:2000]})
        if isinstance(result, ClassifiedIntent):
            return result.intent
        if isinstance(result, dict) and result.get("intent") in {
            "knowledge",
            "contact",
            "unsupported",
        }:
            return result["intent"]
    except Exception:
        logger.info("intent_llm_unavailable fallback=rules_or_knowledge")
    return None


def classify_intent(question: str) -> Intent:
    ruled = classify_with_rules(question)
    if ruled is not None:
        return ruled
    llm_intent = classify_with_llm(question)
    if llm_intent is not None:
        return llm_intent
    return "knowledge"
