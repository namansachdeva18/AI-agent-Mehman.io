"""Unit tests for the SQLite database layer and complete dataset integrity audits.

Tests schema creation, foreign key constraints, seed data integrity,
relational queries, and absence of orphan or inconsistent records.
"""

import sqlite3
import pytest

from app.database.connection import Database
from app.database.seed import seed_database, REFERENCE_START_DATE, INVENTORY_DAYS


@pytest.fixture
def test_db():
    """Create an isolated, seeded in-memory SQLite database for testing."""
    db = Database(":memory:")
    db.connect()
    seed_database(db)
    yield db
    db.close()


class TestDatabaseSchema:
    """Test table creation and schema constraints."""

    def test_tables_created(self, test_db):
        """Verify all 9 expected tables exist."""
        cursor = test_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = {row["name"] for row in cursor.fetchall()}
        expected_tables = {
            "properties",
            "rooms",
            "amenities",
            "property_amenities",
            "room_amenities",
            "policies",
            "add_ons",
            "availability",
            "booking_holds",
        }
        assert expected_tables.issubset(tables)

    def test_foreign_keys_enabled(self, test_db):
        """Verify foreign key enforcement is active."""
        cursor = test_db.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1

    def test_foreign_key_violation_raises(self, test_db):
        """Attempting to insert a room for nonexistent property should fail."""
        with pytest.raises(sqlite3.IntegrityError):
            test_db.execute(
                """
                INSERT INTO rooms (property_id, name, description, max_guests, max_adults,
                                   base_price_per_night, room_size_sqft, bed_type, total_units)
                VALUES (999, 'Phantom Room', 'Desc', 2, 2, 5000.0, 300, 'King', 1)
                """
            )


class TestDatasetIntegrityAudit:
    """Comprehensive dataset integrity audit (Audit 3)."""

    def test_properties_count(self, test_db):
        """Must have exactly 3 properties."""
        count = test_db.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
        assert count == 3

    def test_rooms_count(self, test_db):
        """Must have exactly 9 room types (3 per property)."""
        count = test_db.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        assert count == 9
        per_prop = test_db.execute(
            "SELECT property_id, COUNT(*) as cnt FROM rooms GROUP BY property_id"
        ).fetchall()
        assert len(per_prop) == 3
        assert all(row["cnt"] == 3 for row in per_prop)

    def test_total_availability_count(self, test_db):
        """Must have exactly 3,285 availability records (9 rooms * 365 days)."""
        count = test_db.execute("SELECT COUNT(*) FROM availability").fetchone()[0]
        assert count == 3285

    def test_availability_dates_per_room(self, test_db):
        """Every room must have exactly 365 distinct dates."""
        per_room = test_db.execute(
            "SELECT room_id, COUNT(DISTINCT date) as date_cnt FROM availability GROUP BY room_id"
        ).fetchall()
        assert len(per_room) == 9
        assert all(row["date_cnt"] == 365 for row in per_room)

    def test_no_duplicate_availability(self, test_db):
        """No duplicate (room_id, date) pairs."""
        duplicates = test_db.execute(
            """
            SELECT room_id, date, COUNT(*) as cnt
            FROM availability
            GROUP BY room_id, date
            HAVING cnt > 1
            """
        ).fetchall()
        assert len(duplicates) == 0

    def test_no_orphan_rooms(self, test_db):
        """Every room must point to a valid property."""
        orphans = test_db.execute(
            "SELECT r.id FROM rooms r LEFT JOIN properties p ON r.property_id = p.id WHERE p.id IS NULL"
        ).fetchall()
        assert len(orphans) == 0

    def test_no_orphan_availability(self, test_db):
        """Every availability row must point to a valid room."""
        orphans = test_db.execute(
            "SELECT a.id FROM availability a LEFT JOIN rooms r ON a.room_id = r.id WHERE r.id IS NULL"
        ).fetchall()
        assert len(orphans) == 0

    def test_no_orphan_policies(self, test_db):
        """Every policy must point to a valid property."""
        orphans = test_db.execute(
            "SELECT pol.id FROM policies pol LEFT JOIN properties p ON pol.property_id = p.id WHERE p.id IS NULL"
        ).fetchall()
        assert len(orphans) == 0

    def test_no_orphan_add_ons(self, test_db):
        """Every add-on must point to a valid property."""
        orphans = test_db.execute(
            "SELECT ao.id FROM add_ons ao LEFT JOIN properties p ON ao.property_id = p.id WHERE p.id IS NULL"
        ).fetchall()
        assert len(orphans) == 0

    def test_no_orphan_amenity_junctions(self, test_db):
        """Property and room amenity junctions must not have orphan links."""
        orphan_pa = test_db.execute(
            """
            SELECT pa.property_id, pa.amenity_id FROM property_amenities pa
            LEFT JOIN properties p ON pa.property_id = p.id
            LEFT JOIN amenities a ON pa.amenity_id = a.id
            WHERE p.id IS NULL OR a.id IS NULL
            """
        ).fetchall()
        assert len(orphan_pa) == 0

        orphan_ra = test_db.execute(
            """
            SELECT ra.room_id, ra.amenity_id FROM room_amenities ra
            LEFT JOIN rooms r ON ra.room_id = r.id
            LEFT JOIN amenities a ON ra.amenity_id = a.id
            WHERE r.id IS NULL OR a.id IS NULL
            """
        ).fetchall()
        assert len(orphan_ra) == 0

    def test_no_invalid_pricing_types(self, test_db):
        """Pricing types must strictly be PER_NIGHT, PER_BOOKING, PER_PERSON, or PER_PERSON_PER_NIGHT."""
        valid_types = {"PER_NIGHT", "PER_BOOKING", "PER_PERSON", "PER_PERSON_PER_NIGHT"}
        rows = test_db.execute("SELECT DISTINCT pricing_type FROM add_ons").fetchall()
        types = {r["pricing_type"] for r in rows}
        assert types.issubset(valid_types)

    def test_no_negative_availability(self, test_db):
        """Available units must be non-negative everywhere."""
        negatives = test_db.execute("SELECT COUNT(*) FROM availability WHERE available_units < 0").fetchone()[0]
        assert negatives == 0

    def test_no_invalid_capacities(self, test_db):
        """Max guests must be >= 1 for all rooms."""
        invalid = test_db.execute("SELECT COUNT(*) FROM rooms WHERE max_guests < 1 OR max_adults < 1").fetchone()[0]
        assert invalid == 0

    def test_no_invalid_star_ratings(self, test_db):
        """Star ratings must be between 1.0 and 5.0."""
        invalid = test_db.execute(
            "SELECT COUNT(*) FROM properties WHERE star_rating < 1.0 OR star_rating > 5.0"
        ).fetchone()[0]
        assert invalid == 0
