"""Conversation state manager layer.

Bridges the agent layer with persistent ConversationService in SQLite.
Maintains backward compatibility with Phase 1 in-memory / persistent workflows.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from app.agent.schemas import BookingState, ChatMessage, ConversationState, MessageRole
from app.database.connection import Database
from app.services.conversation import ConversationService, conversation_service


class ConversationStateManager:
    """Manager for active conversation sessions and incremental booking state.

    Supports both in-memory and persistent SQLite-backed operation.
    """

    def __init__(self, db: Database | None = None) -> None:
        self._service = ConversationService(db=db) if db else conversation_service

    def get_or_create(self, session_id: str) -> ConversationState:
        """Retrieve existing persistent conversation or create a new one."""
        try:
            return self._service.get_conversation(session_id)
        except Exception:
            return self._service.create_conversation(conversation_id=session_id)

    def get(self, session_id: str) -> ConversationState | None:
        """Retrieve an existing conversation state, or None if not found."""
        try:
            return self._service.get_conversation(session_id)
        except Exception:
            return None

    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        metadata: dict | None = None,
    ) -> ConversationState:
        """Append a message to the persistent conversation history."""
        self.get_or_create(session_id)
        self._service.append_message(session_id, role, content, metadata)
        return self._service.get_conversation(session_id)

    def update_booking(
        self,
        session_id: str,
        updates: dict[str, Any] | BookingState,
        expected_version: int | None = None,
    ) -> BookingState:
        """Incrementally update the booking state with explicit overrides and persistence."""
        self.get_or_create(session_id)
        conv = self._service.update_booking_state(
            session_id, updates, expected_version=expected_version
        )
        return conv.booking

    def get_missing_fields(self, session_id: str) -> list[str]:
        """Return a list of required booking fields that are still None."""
        state = self.get_or_create(session_id)
        return state.booking.get_missing_search_fields()

    def set_dates(
        self, session_id: str, check_in: date, check_out: date
    ) -> BookingState:
        """Convenience method to set check-in and check-out dates together."""
        return self.update_booking(
            session_id, {"check_in": check_in, "check_out": check_out}
        )

    def reset_booking(self, session_id: str) -> BookingState:
        """Reset the booking state for a session while keeping message history."""
        self.get_or_create(session_id)
        empty = BookingState()
        conv = self._service.update_booking_state(session_id, empty)
        return conv.booking


# Singleton manager instance
state_manager = ConversationStateManager()
