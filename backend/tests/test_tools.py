"""Comprehensive unit tests and targeted audits for the 5 deterministic hotel booking tools.

Audits Covered:
- Audit 1: Booking hold concurrency safety using file-backed SQLite and concurrent threads.
- Audit 2: Amenity search semantics (strict AND logic, property vs room amenity scoping, case-insensitivity).
- Audit 3: Complete dataset integrity (in test_database.py).
- Audit 4: Hold inventory restoration and double-restoration prevention.
- Audit 5: Price override and hold total_price exact consistency.
- Audit 6: Offline Gemini independence verification.
- Tool Unit Tests: search filters, availability boundaries, room specs, 4 pricing models, hold creation.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import tempfile
import pytest

from app.config import settings
from app.database.connection import Database
from app.database.seed import seed_database
from app.errors import AppError, ErrorCode
from app.tools.availability import check_availability
from app.tools.booking_hold import cancel_booking_hold, create_booking_hold, release_expired_holds
from app.tools.contracts import (
    AvailabilityStatus,
    CalculatePriceInput,
    CheckAvailabilityInput,
    CreateBookingHoldInput,
    GetRoomDetailsInput,
    HoldStatus,
    SearchPropertiesInput,
)
from app.tools.pricing import calculate_price
from app.tools.room_details import get_room_details
from app.tools.search import search_properties


@pytest.fixture
def db():
    """Create an isolated, seeded in-memory SQLite database for testing."""
    test_db = Database(":memory:")
    test_db.connect()
    seed_database(test_db)
    yield test_db
    test_db.close()


@pytest.fixture
def file_db():
    """Create a temporary file-backed SQLite database in WAL mode for concurrency testing."""
    temp_dir = tempfile.TemporaryDirectory()
    db_path = Path(temp_dir.name) / "test_concurrency.db"
    test_db = Database(db_path)
    test_db.connect()
    seed_database(test_db)
    test_db.close()
    yield db_path
    temp_dir.cleanup()


# ============================================================
# AUDIT 1: Booking Hold Concurrency Safety
# ============================================================


class TestBookingHoldConcurrencyAudit:
    """Audit 1: Real multi-threaded concurrency safety test for booking holds."""

    def test_concurrent_holds_on_last_available_unit(self, file_db):
        """Simulate two concurrent hold attempts on the final available unit (available_units = 1).

        Expected:
        - Exactly 1 attempt succeeds.
        - Exactly 1 attempt fails with UNAVAILABLE_ROOM.
        - Final available_units in DB is exactly 0 (never -1).
        - Exactly 1 booking_holds record has status HELD.
        """
        setup_db = Database(file_db)
        with setup_db:
            setup_db.execute(
                "UPDATE availability SET available_units = 1 WHERE room_id = 3 AND date = '2026-09-10'"
            )
            setup_db.commit()
        setup_db.close()

        results: list[dict] = []

        def attempt_hold(worker_id: str) -> None:
            worker_db = Database(file_db, timeout=10.0)
            try:
                out = create_booking_hold(
                    CreateBookingHoldInput(
                        room_id=3,
                        check_in=date(2026, 9, 10),
                        check_out=date(2026, 9, 11),
                        guests=2,
                        guest_name=f"Worker {worker_id}",
                        session_id=f"sess-{worker_id}",
                    ),
                    db=worker_db,
                )
                results.append({"status": "SUCCESS", "hold_id": out.hold.hold_id, "worker": worker_id})
            except AppError as e:
                results.append({"status": "FAILED", "code": e.code, "error": str(e), "worker": worker_id})
            finally:
                worker_db.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(attempt_hold, "A")
            f2 = executor.submit(attempt_hold, "B")
            f1.result()
            f2.result()

        successes = [r for r in results if r["status"] == "SUCCESS"]
        failures = [r for r in results if r["status"] == "FAILED"]

        assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
        assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}"
        assert failures[0]["code"] == ErrorCode.UNAVAILABLE_ROOM

        verify_db = Database(file_db)
        with verify_db:
            row = verify_db.execute(
                "SELECT available_units FROM availability WHERE room_id = 3 AND date = '2026-09-10'"
            ).fetchone()
            assert row["available_units"] == 0, f"Expected 0 units, got {row['available_units']}"

            holds = verify_db.execute(
                "SELECT id, guest_name, status FROM booking_holds WHERE room_id = 3 AND status = 'HELD'"
            ).fetchall()
            assert len(holds) == 1
        verify_db.close()


# ============================================================
# AUDIT 2: Amenity Search Semantics & Search Filters
# ============================================================


class TestSearchProperties:
    """Test suite for search_properties tool."""

    def test_search_by_destination_goa(self, db):
        """Should find Azure Sands Beach Resort in Goa."""
        params = SearchPropertiesInput(destination="Goa")
        output = search_properties(params, db=db)

        assert output.total_count == 1
        result = output.results[0]
        assert result.property_name == "Azure Sands Beach Resort"
        assert result.city == "Goa"
        assert len(result.matching_rooms) == 3
        assert result.availability_status == AvailabilityStatus.NOT_CHECKED

    def test_search_by_destination_case_insensitive(self, db):
        """Destination matching should be case-insensitive."""
        params = SearchPropertiesInput(destination="jaipur")
        output = search_properties(params, db=db)

        assert output.total_count == 1
        assert output.results[0].property_name == "The Grand Heritage Palace"

    def test_search_with_dates_sets_availability_status(self, db):
        """When dates are provided, search should perform availability check."""
        params = SearchPropertiesInput(
            destination="Goa",
            check_in=date(2026, 9, 10),
            check_out=date(2026, 9, 13),
            guests=2,
        )
        output = search_properties(params, db=db)

        assert output.total_count == 1
        prop = output.results[0]
        assert prop.availability_status == AvailabilityStatus.AVAILABLE
        assert all(r.available is True for r in prop.matching_rooms)

    def test_search_with_budget_filter(self, db):
        """Budget filter should exclude rooms and properties exceeding budget."""
        params = SearchPropertiesInput(budget_per_night=5000.0)
        output = search_properties(params, db=db)

        assert output.total_count == 1
        prop = output.results[0]
        assert prop.city == "Manali"
        assert all(r.base_price_per_night <= 5000.0 for r in prop.matching_rooms)

    def test_search_with_guest_count_filter(self, db):
        """Guest count should only match rooms capable of holding that many guests."""
        params = SearchPropertiesInput(destination="Goa", guests=5)
        output = search_properties(params, db=db)

        assert output.total_count == 1
        rooms = output.results[0].matching_rooms
        assert len(rooms) >= 1
        assert all(r.max_guests >= 5 for r in rooms)

    def test_single_property_level_amenity(self, db):
        """Property-level amenity ('Temperature-Controlled Pool') matches Grand Heritage Palace rooms."""
        params = SearchPropertiesInput(amenities=["Temperature-Controlled Pool"])
        out = search_properties(params, db=db)
        assert out.total_count == 1
        assert out.results[0].property_name == "The Grand Heritage Palace"

    def test_single_room_level_amenity_scoping(self, db):
        """Room-level amenity ('Private Balcony') must only match rooms that actually have it."""
        params = SearchPropertiesInput(destination="Jaipur", amenities=["Private Balcony"])
        out = search_properties(params, db=db)
        assert out.total_count == 1
        matching_room_ids = {r.room_id for r in out.results[0].matching_rooms}
        assert 2 in matching_room_ids
        assert 3 in matching_room_ids
        assert 1 not in matching_room_ids

    def test_mixed_property_and_room_level_amenities(self, db):
        """Must satisfy BOTH property amenity ('Heritage Spa & Wellness') AND room amenity ('Private Balcony')."""
        params = SearchPropertiesInput(
            amenities=["Heritage Spa & Wellness", "Private Balcony"]
        )
        out = search_properties(params, db=db)
        assert out.total_count == 1
        prop = out.results[0]
        assert prop.property_name == "The Grand Heritage Palace"
        matching_ids = {r.room_id for r in prop.matching_rooms}
        assert matching_ids == {2, 3}

    def test_case_insensitive_amenity_matching(self, db):
        """Matches regardless of casing ('swimming pool', 'SWIMMING POOL', 'Swimming Pool')."""
        for query in ["swimming pool", "SWIMMING POOL", "Swimming Pool"]:
            out = search_properties(SearchPropertiesInput(amenities=[query]), db=db)
            assert out.total_count >= 1
            names = [p.property_name for p in out.results]
            assert "Azure Sands Beach Resort" in names

    def test_search_with_room_preference(self, db):
        """Should match room preference keywords like 'Balcony' or 'Villa'."""
        params = SearchPropertiesInput(destination="Goa", room_preferences=["Villa"])
        output = search_properties(params, db=db)

        assert output.total_count == 1
        rooms = output.results[0].matching_rooms
        assert len(rooms) == 1
        assert "Villa" in rooms[0].name

    def test_search_no_match(self, db):
        """Searching for an unseeded city should return 0 results cleanly."""
        params = SearchPropertiesInput(destination="Kolkata")
        output = search_properties(params, db=db)

        assert output.total_count == 0
        assert output.results == []


# ============================================================
# Check Availability Tests
# ============================================================


class TestCheckAvailability:
    """Test suite for check_availability tool."""

    def test_available_room_checkout_exclusive(self, db):
        """Should verify stay nights = (check_out - check_in).days with checkout-exclusive semantics."""
        params = CheckAvailabilityInput(
            room_id=1,
            check_in=date(2026, 9, 10),
            check_out=date(2026, 9, 13),
            guests=2,
        )
        output = check_availability(params, db=db)

        assert output.nights == 3
        assert len(output.rooms) == 1
        room_res = output.rooms[0]
        assert room_res.available is True
        assert room_res.available_units > 0
        assert room_res.unavailability_reason is None
        assert room_res.unavailable_dates == []

    def test_sold_out_date_scenario(self, db):
        """Room 1 is seeded with 0 units on 2026-10-15."""
        params = CheckAvailabilityInput(
            room_id=1,
            check_in=date(2026, 10, 14),
            check_out=date(2026, 10, 17),
            guests=2,
        )
        output = check_availability(params, db=db)

        room_res = output.rooms[0]
        assert room_res.available is False
        assert room_res.unavailability_reason == "sold_out"
        assert "2026-10-15" in room_res.unavailable_dates

    def test_checkout_date_not_counted_as_stay_night(self, db):
        """Checkout morning on sold-out date (2026-10-15) must be available for 2026-10-13 -> 2026-10-15."""
        params = CheckAvailabilityInput(
            room_id=1,
            check_in=date(2026, 10, 13),
            check_out=date(2026, 10, 15),
            guests=2,
        )
        output = check_availability(params, db=db)

        assert output.rooms[0].available is True

    def test_date_outside_inventory_range(self, db):
        """Dates outside seeded 365-day range should be reported as outside_inventory_range."""
        params = CheckAvailabilityInput(
            room_id=1,
            check_in=date(2028, 1, 10),
            check_out=date(2028, 1, 12),
            guests=2,
        )
        output = check_availability(params, db=db)

        assert output.rooms[0].available is False
        assert output.rooms[0].unavailability_reason == "outside_inventory_range"

    def test_capacity_exceeded(self, db):
        """Room 1 max capacity is 2. Requesting 4 should report capacity_exceeded."""
        params = CheckAvailabilityInput(
            room_id=1,
            check_in=date(2026, 9, 10),
            check_out=date(2026, 9, 12),
            guests=4,
        )
        output = check_availability(params, db=db)

        assert output.rooms[0].available is False
        assert output.rooms[0].unavailability_reason == "capacity_exceeded"

    def test_invalid_date_order_raises(self, db):
        """Check-in after check-out must raise AppError(INVALID_DATES)."""
        params = CheckAvailabilityInput(
            room_id=1,
            check_in=date(2026, 9, 15),
            check_out=date(2026, 9, 10),
        )
        with pytest.raises(AppError) as exc_info:
            check_availability(params, db=db)
        assert exc_info.value.code == ErrorCode.INVALID_DATES

    def test_nonexistent_room_raises(self, db):
        """Nonexistent room ID must raise AppError(UNKNOWN_INFORMATION)."""
        params = CheckAvailabilityInput(
            room_id=9999,
            check_in=date(2026, 9, 10),
            check_out=date(2026, 9, 12),
        )
        with pytest.raises(AppError) as exc_info:
            check_availability(params, db=db)
        assert exc_info.value.code == ErrorCode.UNKNOWN_INFORMATION


# ============================================================
# Room Details Tests
# ============================================================


class TestGetRoomDetails:
    """Test suite for get_room_details tool."""

    def test_valid_room_details_clean_domain_output(self, db):
        """Should return comprehensive room, property, amenities, policies, and add-ons."""
        params = GetRoomDetailsInput(room_id=2)
        output = get_room_details(params, db=db)

        room = output.room
        assert room.room_id == 2
        assert room.room_name == "Royal Courtyard Suite"
        assert room.property_name == "The Grand Heritage Palace"
        assert room.city == "Jaipur"
        assert room.base_price_per_night == 22000.0
        assert room.max_guests == 3
        assert len(room.amenities) >= 1
        assert len(room.property_amenities) >= 1
        assert len(room.policies) >= 3
        assert len(room.available_add_ons) >= 3

    def test_invalid_room_raises_not_found(self, db):
        """Nonexistent room ID must raise AppError(UNKNOWN_INFORMATION)."""
        params = GetRoomDetailsInput(room_id=999)
        with pytest.raises(AppError) as exc_info:
            get_room_details(params, db=db)
        assert exc_info.value.code == ErrorCode.UNKNOWN_INFORMATION


# ============================================================
# Price Calculation Tests
# ============================================================


class TestCalculatePrice:
    """Test suite for calculate_price tool."""

    def test_price_single_night_no_addons(self, db):
        """1 night stay room total calculation."""
        params = CalculatePriceInput(
            room_id=7,
            check_in=date(2026, 9, 1),
            check_out=date(2026, 9, 2),
            guests=2,
        )
        output = calculate_price(params, db=db)
        b = output.breakdown

        assert b.nights == 1
        assert b.room_total == 2800.0
        assert b.add_ons_total == 0.0
        assert b.grand_total == 2800.0

    def test_all_four_addon_pricing_models(self, db):
        """Verify mathematical formulas for PER_BOOKING, PER_NIGHT, PER_PERSON, and PER_PERSON_PER_NIGHT."""
        # Dynamically query Azure Sands Beach Resort (property_id=2) add-on IDs
        goa_addons = db.execute(
            "SELECT id, pricing_type FROM add_ons WHERE property_id = 2 AND active = 1"
        ).fetchall()
        goa_addon_ids = [r["id"] for r in goa_addons]
        assert len(goa_addon_ids) == 4

        params = CalculatePriceInput(
            room_id=4,
            check_in=date(2026, 9, 10),
            check_out=date(2026, 9, 13),
            guests=2,
            selected_add_ons=goa_addon_ids,
        )
        output = calculate_price(params, db=db)
        b = output.breakdown

        assert b.nights == 3
        assert b.room_total == 19500.0
        assert b.add_ons_total == 12300.0
        assert b.grand_total == 31800.0
        assert len(b.add_on_items) == 4

    def test_price_with_seasonal_override(self, db):
        """Room 5 has seasonal price override = ₹15,000 during 2026-12-20 to 2026-12-31."""
        params = CalculatePriceInput(
            room_id=5,
            check_in=date(2026, 12, 24),
            check_out=date(2026, 12, 26),
            guests=4,
        )
        output = calculate_price(params, db=db)
        b = output.breakdown

        assert b.nights == 2
        assert b.room_total == 30000.0
        assert all(nr.is_override for nr in b.nightly_rates)

    def test_capacity_violation_raises(self, db):
        """Exceeding room max capacity should raise CAPACITY_ERROR."""
        params = CalculatePriceInput(
            room_id=1,
            check_in=date(2026, 9, 10),
            check_out=date(2026, 9, 12),
            guests=4,
        )
        with pytest.raises(AppError) as exc_info:
            calculate_price(params, db=db)
        assert exc_info.value.code == ErrorCode.CAPACITY_ERROR

    def test_cross_property_addon_rejected(self, db):
        """Attempting to apply an add-on from Jaipur hotel to a Goa hotel room must fail."""
        # Query an add-on belonging to Jaipur (property_id=1)
        jaipur_addon = db.execute(
            "SELECT id FROM add_ons WHERE property_id = 1 AND active = 1 LIMIT 1"
        ).fetchone()
        assert jaipur_addon is not None

        params = CalculatePriceInput(
            room_id=4,
            check_in=date(2026, 9, 10),
            check_out=date(2026, 9, 12),
            guests=2,
            selected_add_ons=[jaipur_addon["id"]],
        )
        with pytest.raises(AppError) as exc_info:
            calculate_price(params, db=db)
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST


# ============================================================
# AUDIT 4: Hold Inventory Restoration & Double-Restoration Prevention
# ============================================================


class TestHoldInventoryRestorationAudit:
    """Audit 4: Verify complete hold lifecycle and prevent duplicate inventory restoration."""

    def test_hold_expiration_and_double_restore_prevention(self, db):
        """Verify:
        Initial: N
        Hold: N - 1
        Expire: N
        Call release_expired_holds again: remains N (never N + 1).
        """
        initial = db.execute(
            "SELECT available_units FROM availability WHERE room_id = 6 AND date = '2026-09-15'"
        ).fetchone()["available_units"]

        hold_out = create_booking_hold(
            CreateBookingHoldInput(
                room_id=6,
                check_in=date(2026, 9, 15),
                check_out=date(2026, 9, 18),
                guests=4,
            ),
            db=db,
        )
        after_hold = db.execute(
            "SELECT available_units FROM availability WHERE room_id = 6 AND date = '2026-09-15'"
        ).fetchone()["available_units"]
        assert after_hold == initial - 1

        future = datetime.now(UTC) + timedelta(minutes=20)
        released_1 = release_expired_holds(as_of=future, db=db)
        assert released_1 == 1

        after_release = db.execute(
            "SELECT available_units FROM availability WHERE room_id = 6 AND date = '2026-09-15'"
        ).fetchone()["available_units"]
        assert after_release == initial

        released_2 = release_expired_holds(as_of=future + timedelta(minutes=10), db=db)
        assert released_2 == 0

        after_second = db.execute(
            "SELECT available_units FROM availability WHERE room_id = 6 AND date = '2026-09-15'"
        ).fetchone()["available_units"]
        assert after_second == initial

    def test_cancel_hold_double_cancel_prevention(self, db):
        """Cancelling a hold twice must not restore inventory twice."""
        initial = db.execute(
            "SELECT available_units FROM availability WHERE room_id = 4 AND date = '2026-09-10'"
        ).fetchone()["available_units"]

        hold = create_booking_hold(
            CreateBookingHoldInput(
                room_id=4,
                check_in=date(2026, 9, 10),
                check_out=date(2026, 9, 12),
                guests=2,
            ),
            db=db,
        )
        assert db.execute("SELECT available_units FROM availability WHERE room_id = 4 AND date = '2026-09-10'").fetchone()["available_units"] == initial - 1

        ok1 = cancel_booking_hold(hold.hold.hold_id, db=db)
        assert ok1 is True
        assert db.execute("SELECT available_units FROM availability WHERE room_id = 4 AND date = '2026-09-10'").fetchone()["available_units"] == initial

        ok2 = cancel_booking_hold(hold.hold.hold_id, db=db)
        assert ok2 is False
        assert db.execute("SELECT available_units FROM availability WHERE room_id = 4 AND date = '2026-09-10'").fetchone()["available_units"] == initial


# ============================================================
# AUDIT 5: Price Override & Hold Consistency
# ============================================================


class TestPriceConsistencyAudit:
    """Audit 5: Verify calculate_price and create_booking_hold produce identical total_price."""

    def test_price_override_and_hold_consistency(self, db):
        """Room 5 festive override stay with add-ons must match exactly between calculation and hold creation."""
        # Query active add-ons for Azure Sands Beach Resort (property_id=2): Buffet Breakfast & Airport Shuttle
        addon_rows = db.execute(
            "SELECT id FROM add_ons WHERE property_id = 2 AND name IN ('Buffet Breakfast', 'Airport Shuttle (One Way)') ORDER BY id"
        ).fetchall()
        selected_ids = [r["id"] for r in addon_rows]
        assert len(selected_ids) == 2

        calc_input = CalculatePriceInput(
            room_id=5,
            check_in=date(2026, 12, 24),
            check_out=date(2026, 12, 27),
            guests=3,
            selected_add_ons=selected_ids,
        )
        calc_out = calculate_price(calc_input, db=db)
        assert calc_out.breakdown.room_total == 45000.0
        assert calc_out.breakdown.add_ons_total == 6600.0
        assert calc_out.breakdown.grand_total == 51600.0

        hold_input = CreateBookingHoldInput(
            room_id=5,
            check_in=date(2026, 12, 24),
            check_out=date(2026, 12, 27),
            guests=3,
            guest_name="Pooja Mehta",
            selected_add_ons=selected_ids,
        )
        hold_out = create_booking_hold(hold_input, db=db)

        assert hold_out.hold.total_price == calc_out.breakdown.grand_total
        assert hold_out.hold.total_price == 51600.0


# ============================================================
# AUDIT 6: Zero Gemini Dependency
# ============================================================


class TestOfflineIndependenceAudit:
    """Audit 6: Verify all tools execute 100% offline without Gemini."""

    def test_all_tools_work_without_gemini_key(self, db, monkeypatch):
        """Force GEMINI_API_KEY to empty and execute all 5 tools."""
        monkeypatch.setattr(settings, "gemini_api_key", "")

        s_out = search_properties(SearchPropertiesInput(destination="Goa"), db=db)
        assert s_out.total_count == 1

        a_out = check_availability(
            CheckAvailabilityInput(
                room_id=4,
                check_in=date(2026, 9, 10),
                check_out=date(2026, 9, 12),
                guests=2,
            ),
            db=db,
        )
        assert a_out.rooms[0].available is True

        r_out = get_room_details(GetRoomDetailsInput(room_id=4), db=db)
        assert r_out.room.room_name == "Superior Ocean View Room"

        p_out = calculate_price(
            CalculatePriceInput(
                room_id=4,
                check_in=date(2026, 9, 10),
                check_out=date(2026, 9, 12),
                guests=2,
            ),
            db=db,
        )
        assert p_out.breakdown.grand_total == 13000.0

        h_out = create_booking_hold(
            CreateBookingHoldInput(
                room_id=4,
                check_in=date(2026, 9, 10),
                check_out=date(2026, 9, 12),
                guests=2,
            ),
            db=db,
        )
        assert h_out.hold.status == HoldStatus.HELD
