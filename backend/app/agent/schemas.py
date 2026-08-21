"""Core domain models for the Mehman.io hotel booking agent.

This module defines ALL structured types used across the application:
- Hotel/property domain models (source of truth: database)
- Conversation and booking state models (source of truth: application persistence)
- Agent decision and tool execution models (source of truth: orchestrator)

Design principles:
- All fields that may be unknown use Optional with None default
- BookingState supports incremental/partial updates and explicit overrides
- Strict type validation using Pydantic v2
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from app.tools.contracts import HoldStatus


# ============================================================
# Hotel Domain Models (Source of truth: SQLite Database)
# ============================================================


class Amenity(BaseModel):
    """Normalized amenity."""

    id: int
    name: str
    category: str = "general"


class Policy(BaseModel):
    """Hotel policy."""

    id: int
    property_id: int
    policy_type: str
    description: str


class AddOn(BaseModel):
    """Optional add-on service."""

    id: int
    property_id: int
    name: str
    description: str
    price: float
    pricing_type: str  # PER_NIGHT, PER_BOOKING, PER_PERSON, PER_PERSON_PER_NIGHT
    active: bool = True


class Room(BaseModel):
    """Room type belonging to a property."""

    id: int
    property_id: int
    name: str
    description: str = ""
    max_guests: int = 2
    max_adults: int = 2
    max_children: int = 0
    max_occupancy: Optional[int] = None
    base_price_per_night: float = 0.0
    room_size_sqft: int = 300
    bed_type: str = "King"
    total_units: int = 1
    status: str = "active"
    amenities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_occupancy(self) -> "Room":
        if self.max_occupancy is not None and self.max_guests == 2:
            self.max_guests = self.max_occupancy
        elif self.max_occupancy is None:
            self.max_occupancy = self.max_guests
        return self


class Availability(BaseModel):
    """Nightly room availability record."""

    id: int
    room_id: int
    date: date
    available_units: int
    price_override: Optional[float] = None


class Property(BaseModel):
    """Hotel property."""

    id: int
    name: str
    location: Optional[str] = None
    city: str = ""
    state: str = ""
    country: str = "India"
    description: str = ""
    star_rating: float = 4.0
    check_in_time: str = "14:00"
    check_out_time: str = "11:00"
    address: str = ""
    amenities: list[str] = Field(default_factory=list)
    rooms: list[Room] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
    add_ons: list[AddOn] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_location(self) -> "Property":
        if self.location and not self.city:
            self.city = self.location
        elif self.city and not self.location:
            self.location = f"{self.city}, {self.state}" if self.state else self.city
        return self


# ============================================================
# Conversation & Booking State Models
# ============================================================


class ConversationStatus(str, Enum):
    """Status of a conversation session."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


class BookingState(BaseModel):
    """Incremental booking state accumulated during a conversation.

    Fields are None until extracted from user input or selected.
    Supports partial updates — only explicitly provided fields are updated.
    """

    destination: Optional[str] = None
    check_in: Optional[date] = None
    check_out: Optional[date] = None
    guests: Optional[int] = None
    adults: Optional[int] = None
    children: Optional[int] = None
    budget_per_night: Optional[float] = None
    budget_mode: str = "MAX"  # MAX, TARGET, FLEXIBLE
    traveler_type: str = "STANDARD"  # FAMILY, COUPLE, LUXURY, BUDGET, BUSINESS, GROUP, SOLO, STANDARD
    preferred_amenities: list[str] = Field(default_factory=list)
    amenities: list[str] = Field(default_factory=list)
    room_preferences: list[str] = Field(default_factory=list)
    special_requirements: list[str] = Field(default_factory=list)
    selected_property_id: Optional[int] = None
    selected_property_name: Optional[str] = None
    selected_room_id: Optional[int] = None
    selected_room_name: Optional[str] = None
    selected_add_on_ids: list[int] = Field(default_factory=list)
    guest_name: Optional[str] = None
    hold_id: Optional[str] = None
    hold_total_price: Optional[float] = None
    hold_expires_at: Optional[str] = None

    @model_validator(mode="after")
    def reconcile_state(self) -> "BookingState":
        # 1. Date consistency
        if self.check_in and self.check_out and self.check_in >= self.check_out:
            raise ValueError("Check-out date must be strictly after check-in date.")

        # 2. Guest count bounds
        if self.guests is not None and self.guests < 1:
            raise ValueError("Total guests must be at least 1.")

        if self.adults is not None and self.adults < 1:
            raise ValueError("Adult count must be at least 1.")

        if self.children is not None and self.children < 0:
            raise ValueError("Children count cannot be negative.")

        # 3. Adults + children consistency check
        if self.adults is not None or self.children is not None:
            total = (self.adults or 0) + (self.children or 0)
            if self.guests is not None and total > 0 and self.guests != total:
                raise ValueError(
                    f"Total guests ({self.guests}) must equal adults ({self.adults or 0}) + children ({self.children or 0})."
                )
            if self.guests is None and total > 0:
                self.guests = total

        # 4. Budget bounds
        if self.budget_per_night is not None and self.budget_per_night <= 0:
            raise ValueError("Budget per night must be a positive amount.")

        # 5. Amenities sync
        if self.preferred_amenities and not self.amenities:
            self.amenities = self.preferred_amenities
        elif self.amenities and not self.preferred_amenities:
            self.preferred_amenities = self.amenities
        return self

    @property
    def is_complete(self) -> bool:
        """True if all core fields (destination, dates, guests) are filled."""
        return bool(self.destination and self.check_in and self.check_out and self.guests)

    @property
    def is_search_ready(self) -> bool:
        """True if minimum fields for hotel search are known."""
        return bool(
            self.destination
            and self.check_in
            and self.check_out
            and self.guests
            and self.guests >= 1
            and self.check_in < self.check_out
        )

    def get_missing_search_fields(self) -> list[str]:
        """Return list of mandatory search fields still missing."""
        missing: list[str] = []
        if not self.destination:
            missing.append("destination")
        if not self.check_in:
            missing.append("check_in")
        if not self.check_out:
            missing.append("check_out")
        if not self.guests:
            missing.append("guests")
        return missing


class MessageRole(str, Enum):
    """Role of a message author in the conversation."""

    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"
    TOOL = "TOOL"
    GUEST = "guest"
    AGENT = "agent"


class ChatMessage(BaseModel):
    """A single chat message in the conversation history."""

    id: Optional[int] = None
    role: MessageRole
    content: str
    sequence_number: int = 1
    metadata: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConversationState(BaseModel):
    """Persistent state of an active or past conversation session."""

    session_id: str
    status: ConversationStatus = ConversationStatus.ACTIVE
    messages: list[ChatMessage] = Field(default_factory=list)
    booking: BookingState = Field(default_factory=BookingState)
    current_hold_id: Optional[str] = None
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ============================================================
# Agent Decision & Intent Models
# ============================================================


class AgentIntent(str, Enum):
    """Detected user intent from conversational message."""

    SEARCH_HOTELS = "SEARCH_HOTELS"
    RECOMMEND_PROPERTIES = "RECOMMEND_PROPERTIES"
    COMPARE_PROPERTIES = "COMPARE_PROPERTIES"
    CHECK_AVAILABILITY = "CHECK_AVAILABILITY"
    GET_ROOM_DETAILS = "GET_ROOM_DETAILS"
    CALCULATE_PRICE = "CALCULATE_PRICE"
    CREATE_BOOKING_HOLD = "CREATE_BOOKING_HOLD"
    MODIFY_SEARCH = "MODIFY_SEARCH"
    GENERAL_HOTEL_QUESTION = "GENERAL_HOTEL_QUESTION"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    UNKNOWN = "UNKNOWN"


class NextAction(str, Enum):
    """The high-level action the agent decides to take next."""

    CALL_TOOL = "CALL_TOOL"
    ASK_USER = "ASK_USER"
    SEARCH_HOTELS = "SEARCH_HOTELS"
    SEARCH_PROPERTIES = "SEARCH_PROPERTIES"
    RECOMMEND_PROPERTIES = "RECOMMEND_PROPERTIES"
    COMPARE_PROPERTIES = "COMPARE_PROPERTIES"
    CHECK_AVAILABILITY = "CHECK_AVAILABILITY"
    GET_ROOM_DETAILS = "GET_ROOM_DETAILS"
    CALCULATE_PRICE = "CALCULATE_PRICE"
    CREATE_BOOKING_HOLD = "CREATE_BOOKING_HOLD"
    CONFIRM_BOOKING = "CONFIRM_BOOKING"
    RESPOND = "RESPOND"
    HANDLE_ERROR = "HANDLE_ERROR"


class StatePatch(BaseModel):
    """Incremental extracted parameters from user message."""

    destination: Optional[str] = None
    check_in: Optional[str] = None  # YYYY-MM-DD
    check_out: Optional[str] = None  # YYYY-MM-DD
    guests: Optional[int] = None
    adults: Optional[int] = None
    children: Optional[int] = None
    budget_per_night: Optional[float] = None
    preferred_amenities: list[str] = Field(default_factory=list)
    room_preferences: list[str] = Field(default_factory=list)
    selected_property_id: Optional[int] = None
    selected_room_id: Optional[int] = None
    selected_add_on_ids: list[int] = Field(default_factory=list)
    guest_name: Optional[str] = None


class AgentDecision(BaseModel):
    """The structured decision produced by the agent orchestrator."""

    intent: AgentIntent = AgentIntent.UNKNOWN
    next_action: NextAction
    reason_code: str
    state_patch: StatePatch = Field(default_factory=StatePatch)
    tool_name: Optional[str] = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    direct_response: Optional[str] = None
    user_facing_context: Optional[str] = None


# ============================================================
# Tool Execution Models & Events
# ============================================================


class ToolCall(BaseModel):
    """Record of a tool call executed by the agent."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolResult(BaseModel):
    """Result of a tool execution."""

    tool_name: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolExecutionEvent(BaseModel):
    """Safe execution trace event for frontend observability."""

    event_type: str  # e.g. state_updated, tool_started, tool_completed, tool_failed, response_generated
    tool_name: Optional[str] = None
    duration_ms: Optional[float] = None
    success: bool = True
    error_code: Optional[str] = None
    summary: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ============================================================
# Chat API Request & Response
# ============================================================


class ChatApiRequest(BaseModel):
    """Request payload for POST /api/chat."""

    conversation_id: Optional[str] = None
    message: str


class ChatApiResponse(BaseModel):
    """Response payload for POST /api/chat."""

    conversation_id: str
    message: str
    booking_state: BookingState
    next_action: NextAction
    tool_events: list[ToolExecutionEvent] = Field(default_factory=list)
    agent_decision: Optional[AgentDecision] = None
