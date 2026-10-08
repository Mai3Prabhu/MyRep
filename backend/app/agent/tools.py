"""Narrow typed application tool for recording a contact request.

The LLM does not choose profile_id. The application binds it from the
authorized request path before the tool runs.
"""

from __future__ import annotations

import uuid

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.services import contact_service


class CreateContactRequestInput(BaseModel):
    visitor_message: str = Field(..., min_length=1, max_length=4000)


def make_create_contact_request_tool(db: Session, profile_id: uuid.UUID) -> StructuredTool:
    def _run(visitor_message: str) -> dict:
        return contact_service.create_contact_request(
            db=db,
            profile_id=profile_id,
            visitor_message=visitor_message,
        )

    return StructuredTool.from_function(
        name="create_contact_request",
        description=(
            "Record a pending contact/handoff request for the authorized profile. "
            "Does not send email or deliver a message."
        ),
        func=_run,
        args_schema=CreateContactRequestInput,
    )
