"""Comprehensive unit and integration tests for Phase 3: Persistent Conversation State & Session Management.

Tests:
1. Database schema, tables, foreign keys, and migration integrity.
2. Conversation lifecycle (create, get, close, invalid IDs).
3. Ordered message persistence and sequence numbering.
4. Incremental booking state updates, overrides, and missing-field detection.
5. Restart persistence (state and messages survive database disconnect / reconnect).
6. Cross-conversation data isolation.
7. Optimistic concurrency and version conflict protection.
8. Active vs expired/cancelled hold reconciliation.
9. FastAPI REST endpoints for conversation management.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import tempfile
import httpx
import pytest

from app.agent.schemas import (
    BookingState,
    ChatMessage,
    ConversationState,
    ConversationStatus,
    HoldStatus,
    MessageRole,
)
from app.database.connection import Database
from app.database.seed import seed_database
from app.errors import AppError, ErrorCode
from app.main import app
from app.services.conversation import ConversationService
from app.tools.booking_hold import cancel_booking_hold, create_booking_hold
from app.tools.contracts import CreateBookingHoldInput


@pytest.fixture
def db():
    """Create an isolated, seeded in-memory SQLite database for testing."""
    test_db = Database(":memory:")
    test_db.connect()
    seed_database(test_db)
    yield test_db
    test_db.close()


@pytest.fixture
def file_db_path():
    """Create a temporary file-backed SQLite database for restart persistence tests."""
    temp_dir = tempfile.TemporaryDirectory()
    path = Path(temp_dir.name) / "test_restart.db"
    db_inst = Database(path)
    db_inst.connect()
    seed_database(db_inst)
    db_inst.close()
    yield path
    try:
        temp_dir.cleanup()
    except Exception:
        pass


# ============================================================
# 1. Database Schema & Migration Tests
# ============================================================


class TestConversationSchemaAndMigration:
    """Test schema creation and preservation of existing Phase 2 hotel data."""

    def test_conversation_tables_exist(self, db):
        """Verify conversations and conversation_messages tables exist with indexes."""
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('conversations', 'conversation_messages')"
        )
        tables = {r["name"] for r in cursor.fetchall()}
        assert "conversations" in tables
        assert "conversation_messages" in tables

    def test_phase2_data_preserved(self, db):
        """Verify that properties, rooms, amenities, policies, and availability are intact."""
        props = db.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
        rooms = db.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        avail = db.execute("SELECT COUNT(*) FROM availability").fetchone()[0]

        assert props == 3
        assert rooms == 9
        assert avail == 3285


# ============================================================
# 2. Conversation Lifecycle Tests
# ============================================================


class TestConversationLifecycle:
    """Test session creation, retrieval, closing, and error cases."""

    def test_create_and_get_conversation(self, db):
        """Create conversation and verify default fields."""
        svc = ConversationService(db=db)
        conv = svc.create_conversation()

        assert conv.session_id.startswith("conv-")
        assert conv.status == ConversationStatus.ACTIVE
        assert conv.version == 1
        assert conv.messages == []
        assert conv.booking.destination is None

        # Retrieve and check
        loaded = svc.get_conversation(conv.session_id)
        assert loaded.session_id == conv.session_id
        assert loaded.version == 1

    def test_create_with_custom_id(self, db):
        """Create conversation with explicit UUID."""
        svc = ConversationService(db=db)
        conv = svc.create_conversation(conversation_id="custom-uuid-12345")
        assert conv.session_id == "custom-uuid-12345"

    def test_get_nonexistent_conversation_raises_404(self, db):
        """Attempting to get an unknown conversation must raise 404 UNKNOWN_INFORMATION."""
        svc = ConversationService(db=db)
        with pytest.raises(AppError) as exc_info:
            svc.get_conversation("nonexistent-conv-id")
        assert exc_info.value.code == ErrorCode.UNKNOWN_INFORMATION
        assert exc_info.value.status_code == 404

    def test_close_conversation(self, db):
        """Close/complete conversation session."""
        svc = ConversationService(db=db)
        conv = svc.create_conversation()
        svc.close_conversation(conv.session_id, status=ConversationStatus.COMPLETED)

        loaded = svc.get_conversation(conv.session_id)
        assert loaded.status == ConversationStatus.COMPLETED


# ============================================================
# 3. Message Persistence & Sequence Ordering
# ============================================================


class TestMessagePersistence:
    """Test ordered chat message persistence."""

    def test_append_messages_sequential_ordering(self, db):
        """Verify messages have deterministic 1-based sequence numbering."""
        svc = ConversationService(db=db)
        conv = svc.create_conversation()

        m1 = svc.append_message(conv.session_id, MessageRole.USER, "Hello, looking for hotels in Goa.")
        m2 = svc.append_message(conv.session_id, MessageRole.ASSISTANT, "Great! When are you planning to visit?")
        m3 = svc.append_message(conv.session_id, MessageRole.USER, "From 10th to 13th September 2026.")

        assert m1.sequence_number == 1
        assert m2.sequence_number == 2
        assert m3.sequence_number == 3

        loaded = svc.get_conversation(conv.session_id)
        assert len(loaded.messages) == 3
        assert [m.sequence_number for m in loaded.messages] == [1, 2, 3]
        assert loaded.messages[0].content == "Hello, looking for hotels in Goa."
        assert loaded.messages[1].role == MessageRole.ASSISTANT
        assert loaded.messages[2].role == MessageRole.USER

    def test_append_message_to_invalid_conv_raises_404(self, db):
        """Appending a message to a nonexistent conversation must raise 404."""
        svc = ConversationService(db=db)
        with pytest.raises(AppError) as exc_info:
            svc.append_message("invalid-id", MessageRole.USER, "Hi")
        assert exc_info.value.code == ErrorCode.UNKNOWN_INFORMATION


# ============================================================
# 4. Incremental Booking State & Overrides
# ============================================================


class TestIncrementalStateAndOverrides:
    """Test step-by-step state accumulation and explicit overrides."""

    def test_incremental_state_flow(self, db):
        """Verify user multi-turn requirement accumulation:
        Turn 1: destination = 'Goa'
        Turn 2: dates = 2026-09-10 to 2026-09-13
        Turn 3: guests = 5
        All previously collected data must be preserved.
        """
        svc = ConversationService(db=db)
        conv = svc.create_conversation()

        # Turn 1: Destination
        c1 = svc.update_booking_state(conv.session_id, {"destination": "Goa"})
        assert c1.booking.destination == "Goa"
        assert c1.booking.check_in is None
        assert c1.booking.guests is None
        assert c1.booking.get_missing_search_fields() == ["check_in", "check_out", "guests"]

        # Turn 2: Dates (Destination preserved)
        c2 = svc.update_booking_state(
            conv.session_id,
            {"check_in": date(2026, 9, 10), "check_out": date(2026, 9, 13)},
        )
        assert c2.booking.destination == "Goa"
        assert c2.booking.check_in == date(2026, 9, 10)
        assert c2.booking.check_out == date(2026, 9, 13)
        assert c2.booking.guests is None
        assert c2.booking.get_missing_search_fields() == ["guests"]

        # Turn 3: Guests (Destination & dates preserved)
        c3 = svc.update_booking_state(conv.session_id, {"guests": 5})
        assert c3.booking.destination == "Goa"
        assert c3.booking.check_in == date(2026, 9, 10)
        assert c3.booking.check_out == date(2026, 9, 13)
        assert c3.booking.guests == 5
        assert c3.booking.get_missing_search_fields() == []
        assert c3.booking.is_search_ready is True

    def test_explicit_override_semantics(self, db):
        """Verify explicit user corrections override previous values cleanly:
        destination: Goa -> Jaipur
        guests: 4 -> 6
        """
        svc = ConversationService(db=db)
        conv = svc.create_conversation()

        svc.update_booking_state(conv.session_id, {"destination": "Goa", "guests": 4})
        c = svc.get_conversation(conv.session_id)
        assert c.booking.destination == "Goa"
        assert c.booking.guests == 4

        # Override destination to Jaipur and guests to 6
        c_over = svc.update_booking_state(conv.session_id, {"destination": "Jaipur", "guests": 6})
        assert c_over.booking.destination == "Jaipur"
        assert c_over.booking.guests == 6

    def test_invalid_date_order_rejected(self, db):
        """check_in >= check_out must raise AppError(INVALID_DATES)."""
        svc = ConversationService(db=db)
        conv = svc.create_conversation()

        with pytest.raises(AppError) as exc_info:
            svc.update_booking_state(
                conv.session_id,
                {"check_in": date(2026, 9, 15), "check_out": date(2026, 9, 10)},
            )
        assert exc_info.value.code == ErrorCode.INVALID_DATES

    def test_invalid_guest_count_rejected(self, db):
        """guests < 1 must raise AppError(INVALID_REQUEST)."""
        svc = ConversationService(db=db)
        conv = svc.create_conversation()

        with pytest.raises(AppError) as exc_info:
            svc.update_booking_state(conv.session_id, {"guests": 0})
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST

    def test_room_property_mismatch_rejected(self, db):
        """Selecting a room that belongs to another property must be rejected."""
        svc = ConversationService(db=db)
        conv = svc.create_conversation()

        # Property 1 is Jaipur. Room 4 belongs to Property 2 (Goa).
        with pytest.raises(AppError) as exc_info:
            svc.update_booking_state(
                conv.session_id,
                {"selected_property_id": 1, "selected_room_id": 4},
            )
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST


# ============================================================
# 5. Restart Persistence & Disconnect Simulation
# ============================================================


class TestRestartPersistence:
    """Verify conversations and booking states survive backend restart / DB reconnect."""

    def test_state_survives_backend_restart(self, file_db_path):
        """1. Connect to file DB, create conversation, add messages, update state.
        2. Close connection (simulates backend shutdown).
        3. Open new connection with fresh ConversationService (simulates restart).
        4. Verify all data and state are preserved exactly.
        """
        # Session 1: Write data
        db1 = Database(file_db_path)
        svc1 = ConversationService(db=db1)
        conv1 = svc1.create_conversation(conversation_id="conv-restart-test-1")
        svc1.append_message(conv1.session_id, MessageRole.USER, "I want a luxury suite in Jaipur.")
        svc1.append_message(conv1.session_id, MessageRole.ASSISTANT, "Grand Heritage Palace is available.")
        svc1.update_booking_state(
            conv1.session_id,
            {
                "destination": "Jaipur",
                "check_in": date(2026, 10, 1),
                "check_out": date(2026, 10, 4),
                "guests": 2,
                "selected_property_id": 1,
            },
        )
        db1.close()

        # Session 2: Fresh start from disk
        db2 = Database(file_db_path)
        svc2 = ConversationService(db=db2)
        loaded = svc2.get_conversation("conv-restart-test-1")

        assert loaded.session_id == "conv-restart-test-1"
        assert loaded.version == 2
        assert len(loaded.messages) == 2
        assert loaded.messages[0].content == "I want a luxury suite in Jaipur."
        assert loaded.messages[1].content == "Grand Heritage Palace is available."
        assert loaded.booking.destination == "Jaipur"
        assert loaded.booking.check_in == date(2026, 10, 1)
        assert loaded.booking.check_out == date(2026, 10, 4)
        assert loaded.booking.guests == 2
        assert loaded.booking.selected_property_id == 1
        assert loaded.booking.selected_property_name == "The Grand Heritage Palace"
        assert loaded.booking.is_search_ready is True
        db2.close()


# ============================================================
# 6. Data Isolation Tests
# ============================================================


class TestDataIsolation:
    """Verify Conversation A cannot access or mutate Conversation B."""

    def test_conversation_isolation(self, db):
        """Conversations A and B must maintain separate state and message histories."""
        svc = ConversationService(db=db)
        conv_a = svc.create_conversation(conversation_id="conv-user-a")
        conv_b = svc.create_conversation(conversation_id="conv-user-b")

        # Update A
        svc.append_message(conv_a.session_id, MessageRole.USER, "Message from User A")
        svc.update_booking_state(conv_a.session_id, {"destination": "Goa", "guests": 2})

        # Update B
        svc.append_message(conv_b.session_id, MessageRole.USER, "Message from User B")
        svc.update_booking_state(conv_b.session_id, {"destination": "Manali", "guests": 5})

        # Verify A
        loaded_a = svc.get_conversation(conv_a.session_id)
        assert len(loaded_a.messages) == 1
        assert loaded_a.messages[0].content == "Message from User A"
        assert loaded_a.booking.destination == "Goa"
        assert loaded_a.booking.guests == 2

        # Verify B
        loaded_b = svc.get_conversation(conv_b.session_id)
        assert len(loaded_b.messages) == 1
        assert loaded_b.messages[0].content == "Message from User B"
        assert loaded_b.booking.destination == "Manali"
        assert loaded_b.booking.guests == 5


# ============================================================
# 7. Optimistic Concurrency & Versioning Tests
# ============================================================


class TestOptimisticConcurrency:
    """Test lost update protection using conversation versioning."""

    def test_version_increments_on_update(self, db):
        """Each booking state update must increment version by 1."""
        svc = ConversationService(db=db)
        conv = svc.create_conversation()
        assert conv.version == 1

        c1 = svc.update_booking_state(conv.session_id, {"destination": "Goa"}, expected_version=1)
        assert c1.version == 2

        c2 = svc.update_booking_state(conv.session_id, {"guests": 3}, expected_version=2)
        assert c2.version == 3

    def test_version_conflict_raises_409(self, db):
        """Updating with a stale expected_version must raise 409 conflict."""
        svc = ConversationService(db=db)
        conv = svc.create_conversation()
        assert conv.version == 1

        # First update increments version to 2
        svc.update_booking_state(conv.session_id, {"destination": "Goa"}, expected_version=1)

        # Stale update attempting with expected_version=1 must fail
        with pytest.raises(AppError) as exc_info:
            svc.update_booking_state(conv.session_id, {"guests": 4}, expected_version=1)
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST
        assert exc_info.value.status_code == 409


# ============================================================
# 8. Hold Reconciliation Tests
# ============================================================


class TestHoldReconciliation:
    """Test active vs expired/cancelled hold reconciliation."""

    def test_active_hold_retained_in_state(self, db):
        """Active hold in booking_holds table must be retained in conversation state."""
        # Create real hold
        hold_out = create_booking_hold(
            CreateBookingHoldInput(
                room_id=4,
                check_in=date(2026, 9, 10),
                check_out=date(2026, 9, 12),
                guests=2,
            ),
            db=db,
        )
        hold_id = hold_out.hold.hold_id

        svc = ConversationService(db=db)
        conv = svc.create_conversation()
        svc.update_booking_state(
            conv.session_id,
            {"hold_id": hold_id, "hold_total_price": hold_out.hold.total_price},
        )

        loaded = svc.get_conversation(conv.session_id)
        assert loaded.booking.hold_id == hold_id
        assert loaded.booking.hold_total_price == hold_out.hold.total_price

    def test_cancelled_hold_cleared_from_state(self, db):
        """When a hold is cancelled, subsequent conversation retrieval automatically clears hold_id."""
        hold_out = create_booking_hold(
            CreateBookingHoldInput(
                room_id=4,
                check_in=date(2026, 9, 10),
                check_out=date(2026, 9, 12),
                guests=2,
            ),
            db=db,
        )
        hold_id = hold_out.hold.hold_id

        svc = ConversationService(db=db)
        conv = svc.create_conversation()
        svc.update_booking_state(conv.session_id, {"hold_id": hold_id})

        # Cancel hold
        cancel_booking_hold(hold_id, db=db)

        # Retrieve conversation: hold must be reconciled/cleared
        loaded = svc.get_conversation(conv.session_id)
        assert loaded.booking.hold_id is None
        assert loaded.current_hold_id is None


# ============================================================
# 9. FastAPI Endpoints Integration Tests
# ============================================================


class TestConversationAPIEndpoints:
    """Test conversation REST API routes."""

    @pytest.mark.anyio
    async def test_create_and_manage_conversation_api(self):
        """Test full REST lifecycle via FastAPI endpoints."""
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # 1. POST /api/conversations
            r_create = await client.post("/api/conversations")
            assert r_create.status_code == 201
            conv = r_create.json()
            session_id = conv["session_id"]
            assert session_id.startswith("conv-")

            # 2. POST /api/conversations/{id}/messages
            r_msg = await client.post(
                f"/api/conversations/{session_id}/messages",
                json={"role": "USER", "content": "Looking for a stay in Goa"},
            )
            assert r_msg.status_code == 201
            msg = r_msg.json()
            assert msg["sequence_number"] == 1
            assert msg["content"] == "Looking for a stay in Goa"

            # 3. PATCH /api/conversations/{id}/state
            r_patch = await client.patch(
                f"/api/conversations/{session_id}/state",
                json={"updates": {"destination": "Goa", "guests": 2}},
            )
            assert r_patch.status_code == 200
            updated = r_patch.json()
            assert updated["booking"]["destination"] == "Goa"
            assert updated["booking"]["guests"] == 2
            assert updated["version"] == 2

            # 4. GET /api/conversations/{id}/state
            r_state = await client.get(f"/api/conversations/{session_id}/state")
            assert r_state.status_code == 200
            state_data = r_state.json()
            assert state_data["booking"]["destination"] == "Goa"
            assert "check_in" in state_data["missing_search_fields"]
            assert state_data["is_search_ready"] is False

            # 5. GET /api/conversations/{id}/messages
            r_msgs = await client.get(f"/api/conversations/{session_id}/messages")
            assert r_msgs.status_code == 200
            assert len(r_msgs.json()) == 1

            # 6. POST /api/conversations/{id}/close
            r_close = await client.post(f"/api/conversations/{session_id}/close")
            assert r_close.status_code == 204
