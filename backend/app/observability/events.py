"""Structured execution events for the observability layer.

These events form a safe, UI-visible trace of what the agent did
during a conversation turn. They must NEVER contain private
chain-of-thought or internal LLM reasoning.

Phase 1: Event model definitions.
Phase 8+: Event collection, storage, and UI display.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of structured execution events."""

    MESSAGE_RECEIVED = "message_received"
    STATE_UPDATED = "state_updated"
    DECISION_MADE = "decision_made"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    RESPONSE_GENERATED = "response_generated"
    ERROR_OCCURRED = "error_occurred"


class ExecutionEvent(BaseModel):
    """A single step in the agent's execution trace.

    Safe for frontend display — no private reasoning.
    """

    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str = ""
    summary: str = ""  # short, human-readable description
    data: dict = Field(default_factory=dict)  # structured payload
    error: Optional[str] = None


class ExecutionTrace(BaseModel):
    """Ordered list of events for a single conversation turn."""

    session_id: str
    turn_number: int = 0
    events: list[ExecutionEvent] = Field(default_factory=list)

    def add_event(
        self,
        event_type: EventType,
        summary: str,
        data: dict | None = None,
        error: str | None = None,
    ) -> ExecutionEvent:
        """Append an event to the trace."""
        event = ExecutionEvent(
            event_type=event_type,
            session_id=self.session_id,
            summary=summary,
            data=data or {},
            error=error,
        )
        self.events.append(event)
        return event
