"""Chat API endpoint.

Routes guest messages through the Gemini-powered AgentOrchestrator,
persisting conversation state and executing deterministic tools.
"""

from __future__ import annotations

import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.agent.orchestrator import agent_orchestrator
from app.agent.schemas import BookingState, NextAction, ToolExecutionEvent
from app.errors import AppError, ErrorCode
from app.services.conversation import conversation_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

MAX_MESSAGE_LENGTH = 10000


class ChatRequest(BaseModel):
    """Incoming chat request payload."""

    session_id: Optional[str] = Field(default=None, description="Session/Conversation ID")
    conversation_id: Optional[str] = Field(default=None, description="Alternative key for Conversation ID")
    message: str = Field(description="Guest user message", min_length=1, max_length=MAX_MESSAGE_LENGTH)


class ChatResponse(BaseModel):
    """Comprehensive chat response payload."""

    session_id: str
    conversation_id: str
    reply: str
    message: str
    booking_state: BookingState
    next_action: NextAction
    tool_events: list[ToolExecutionEvent] = Field(default_factory=list)
    agent_implemented: bool = True


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-ID"),
) -> ChatResponse:
    """Process a guest chat message through the agent orchestrator."""
    # 1. Validate non-empty/non-whitespace message content
    cleaned_message = request.message.strip()
    if not cleaned_message:
        raise AppError(
            code=ErrorCode.INVALID_REQUEST,
            message="Message cannot be empty or whitespace only.",
            status_code=400,
        )

    conv_id = request.conversation_id or request.session_id or f"conv-{uuid.uuid4().hex[:12]}"

    # 2. Check conversation status if conversation already exists
    try:
        existing_conv = conversation_service.get_conversation(conv_id)
        if existing_conv.status.value in ("COMPLETED", "ABANDONED"):
            raise AppError(
                code=ErrorCode.CONVERSATION_CLOSED,
                message=f"Conversation '{conv_id}' is {existing_conv.status.value.lower()}. Please start a new conversation.",
                status_code=400,
            )
    except AppError as e:
        if e.code == ErrorCode.CONVERSATION_CLOSED:
            raise
        # Session does not exist yet; will be created on the fly

    # 3. Route to orchestrator
    api_result = await agent_orchestrator.handle_message(
        conversation_id=conv_id,
        user_message=cleaned_message,
    )

    return ChatResponse(
        session_id=api_result.conversation_id,
        conversation_id=api_result.conversation_id,
        reply=api_result.message,
        message=api_result.message,
        booking_state=api_result.booking_state,
        next_action=api_result.next_action,
        tool_events=api_result.tool_events,
        agent_implemented=True,
    )
