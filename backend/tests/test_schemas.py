"""Tests for domain schemas and state management."""

from datetime import date
import pytest

from app.agent.schemas import (
    BookingState,
    ConversationState,
    ChatMessage,
    MessageRole,
    AgentDecision,
    NextAction,
    ToolCall,
    ToolResult,
    Property,
    Room,
    Amenity,
)
from app.agent.state import ConversationStateManager
from app.database.connection import Database


class TestBookingState:
    """Test BookingState creation and partial initialization."""

    def test_empty_booking_state(self):
        """All fields should default to None/empty."""
        state = BookingState()
        assert state.destination is None
        assert state.check_in is None
        assert state.check_out is None
        assert state.guests is None
        assert state.adults is None
        assert state.children is None
        assert state.budget_per_night is None
        assert state.room_preferences == []
        assert state.amenities == []
        assert state.special_requirements == []
        assert state.selected_property_id is None
        assert state.selected_room_id is None

    def test_partial_booking_state(self):
        """Should accept partial data without requiring all fields."""
        state = BookingState(destination="Goa", guests=4)
        assert state.destination == "Goa"
        assert state.guests == 4
        assert state.check_in is None  # still unknown


class TestConversationStateManager:
    """Test incremental state updates."""

    @pytest.fixture(autouse=True)
    def setup_mgr(self):
        self.db = Database(":memory:")
        self.db.connect()
        self.db.create_tables()
        self.mgr = ConversationStateManager(db=self.db)
        yield
        self.db.close()

    def test_create_session(self):
        state = self.mgr.get_or_create("sess-1")
        assert state.session_id == "sess-1"
        assert state.booking.destination is None

    def test_incremental_update_destination(self):
        self.mgr.get_or_create("sess-1")

        booking = self.mgr.update_booking("sess-1", {"destination": "Goa"})
        assert booking.destination == "Goa"
        assert booking.guests is None  # unchanged

    def test_incremental_update_multiple_fields(self):
        self.mgr.get_or_create("sess-1")

        self.mgr.update_booking("sess-1", {"destination": "Goa"})
        self.mgr.update_booking("sess-1", {"guests": 4, "budget_per_night": 20000})

        state = self.mgr.get("sess-1")
        assert state.booking.destination == "Goa"
        assert state.booking.guests == 4
        assert state.booking.budget_per_night == 20000

    def test_incremental_override(self):
        """Guest changes their mind — field should be overridden."""
        self.mgr.get_or_create("sess-1")

        self.mgr.update_booking("sess-1", {"guests": 4})
        self.mgr.update_booking("sess-1", {"guests": 5})

        state = self.mgr.get("sess-1")
        assert state.booking.guests == 5

    def test_unknown_fields_ignored(self):
        """Unknown fields in the update dict should be silently ignored."""
        self.mgr.get_or_create("sess-1")
        self.mgr.update_booking("sess-1", {"nonexistent_field": "value"})

    def test_add_message(self):
        self.mgr.add_message("sess-1", MessageRole.GUEST, "I want to visit Goa")
        state = self.mgr.get("sess-1")
        assert len(state.messages) == 1
        assert state.messages[0].role == MessageRole.GUEST
        assert state.messages[0].content == "I want to visit Goa"

    def test_missing_fields(self):
        self.mgr.get_or_create("sess-1")
        missing = self.mgr.get_missing_fields("sess-1")
        assert "destination" in missing
        assert "check_in" in missing
        assert "check_out" in missing
        assert "guests" in missing

    def test_missing_fields_after_partial_update(self):
        self.mgr.update_booking("sess-1", {"destination": "Goa", "guests": 2})
        missing = self.mgr.get_missing_fields("sess-1")
        assert "destination" not in missing
        assert "guests" not in missing
        assert "check_in" in missing
        assert "check_out" in missing

    def test_set_dates(self):
        self.mgr.update_booking(
            "sess-1",
            {
                "check_in": date(2026, 9, 1),
                "check_out": date(2026, 9, 5),
            },
        )
        state = self.mgr.get("sess-1")
        assert state.booking.check_in == date(2026, 9, 1)
        assert state.booking.check_out == date(2026, 9, 5)


class TestAgentDecision:
    """Test AgentDecision creation."""

    def test_ask_user_decision(self):
        d = AgentDecision(
            next_action=NextAction.ASK_USER,
            reason_code="missing_dates",
            user_facing_context="Please provide check-in and check-out dates.",
        )
        assert d.next_action == NextAction.ASK_USER
        assert d.tool_name is None
        assert d.reason_code == "missing_dates"

    def test_call_tool_decision(self):
        d = AgentDecision(
            next_action=NextAction.CALL_TOOL,
            tool_name="search_properties",
            tool_arguments={"destination": "Goa", "guests": 4},
            reason_code="search_requirements_complete",
        )
        assert d.next_action == NextAction.CALL_TOOL
        assert d.tool_name == "search_properties"


class TestToolModels:
    """Test ToolCall and ToolResult creation."""

    def test_tool_call(self):
        tc = ToolCall(
            tool_name="check_availability",
            arguments={"property_id": 1, "check_in": "2026-09-01"},
        )
        assert tc.tool_name == "check_availability"

    def test_tool_result_success(self):
        tr = ToolResult(
            tool_name="check_availability",
            success=True,
            data={"available": True, "rooms": []},
        )
        assert tr.success is True
        assert tr.error is None

    def test_tool_result_failure(self):
        tr = ToolResult(
            tool_name="check_availability",
            success=False,
            error="Room not found",
        )
        assert tr.success is False
        assert tr.error == "Room not found"


class TestDomainModels:
    """Test hotel domain model instantiation."""

    def test_property_creation(self):
        p = Property(
            id=1,
            name="Ocean View Resort",
            location="Goa",
            star_rating=4.5,
        )
        assert p.name == "Ocean View Resort"
        assert p.rooms == []

    def test_room_creation(self):
        r = Room(
            id=1,
            property_id=1,
            name="Deluxe Sea View",
            base_price_per_night=8500.0,
            max_adults=2,
            max_children=1,
            max_occupancy=3,
        )
        assert r.base_price_per_night == 8500.0
        assert r.max_occupancy == 3

    def test_amenity_creation(self):
        a = Amenity(id=1, name="Swimming Pool", category="recreation")
        assert a.name == "Swimming Pool"
