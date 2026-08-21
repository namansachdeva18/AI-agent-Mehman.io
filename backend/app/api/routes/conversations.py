"""Conversation and session management API routes.

Provides endpoints for creating, retrieving, updating conversations,
adding messages, and managing incremental booking state across sessions.
"""

from typing import Any, Optional
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.agent.schemas import (
    BookingState,
    ChatMessage,
    ConversationState,
    ConversationStatus,
    MessageRole,
)
from app.services.conversation import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    """Request payload for creating a new conversation session."""

    conversation_id: Optional[str] = Field(default=None, description="Optional custom session UUID")


class AppendMessageRequest(BaseModel):
    """Request payload for appending a message to a conversation."""

    role: MessageRole = Field(default=MessageRole.USER, description="Message role (USER, ASSISTANT, etc.)")
    content: str = Field(description="Message text content")
    metadata: dict = Field(default_factory=dict, description="Safe metadata attributes")


class UpdateStateRequest(BaseModel):
    """Request payload for incrementally updating booking state."""

    updates: dict[str, Any] = Field(description="Dictionary of booking fields to update or override")
    expected_version: Optional[int] = Field(default=None, description="Optional version for optimistic locking")


class StateResponse(BaseModel):
    """Response payload for current booking state and missing fields."""

    session_id: str
    version: int
    booking: BookingState
    missing_search_fields: list[str]
    is_search_ready: bool


@router.post("", response_model=ConversationState, status_code=status.HTTP_201_CREATED)
async def create_conversation(req: Optional[CreateConversationRequest] = None) -> ConversationState:
    """Create a new persistent conversation session."""
    conv_id = req.conversation_id if req else None
    return conversation_service.create_conversation(conversation_id=conv_id)


@router.get("/{conversation_id}", response_model=ConversationState)
async def get_conversation(conversation_id: str) -> ConversationState:
    """Retrieve full conversation state, message history, and reconciled booking state."""
    return conversation_service.get_conversation(conversation_id)


@router.post("/{conversation_id}/messages", response_model=ChatMessage, status_code=status.HTTP_201_CREATED)
async def append_message(conversation_id: str, req: AppendMessageRequest) -> ChatMessage:
    """Append a message to the conversation."""
    return conversation_service.append_message(
        conversation_id=conversation_id,
        role=req.role,
        content=req.content,
        metadata=req.metadata,
    )


@router.get("/{conversation_id}/messages", response_model=list[ChatMessage])
async def get_messages(conversation_id: str) -> list[ChatMessage]:
    """Retrieve ordered message history for a conversation."""
    conv = conversation_service.get_conversation(conversation_id)
    return conv.messages


@router.get("/{conversation_id}/state", response_model=StateResponse)
async def get_state(conversation_id: str) -> StateResponse:
    """Get current booking state and missing search fields."""
    conv = conversation_service.get_conversation(conversation_id)
    return StateResponse(
        session_id=conv.session_id,
        version=conv.version,
        booking=conv.booking,
        missing_search_fields=conv.booking.get_missing_search_fields(),
        is_search_ready=conv.booking.is_search_ready,
    )


@router.patch("/{conversation_id}/state", response_model=ConversationState)
async def update_state(conversation_id: str, req: UpdateStateRequest) -> ConversationState:
    """Incrementally update booking state with validation and optimistic locking."""
    return conversation_service.update_booking_state(
        conversation_id=conversation_id,
        updates=req.updates,
        expected_version=req.expected_version,
    )


class CloseConversationRequest(BaseModel):
    status: ConversationStatus = ConversationStatus.COMPLETED


@router.post("/{conversation_id}/close", status_code=status.HTTP_204_NO_CONTENT)
async def close_conversation(
    conversation_id: str,
    req: Optional[CloseConversationRequest] = None,
    status_val: Optional[ConversationStatus] = None,
) -> None:
    """Close or abandon a conversation session."""
    target_status = ConversationStatus.COMPLETED
    if req and req.status:
        target_status = req.status
    elif status_val:
        target_status = status_val
    conversation_service.close_conversation(conversation_id, status=target_status)
