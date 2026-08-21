"""Seed script for the Mehman.io hotel database.

Populates the SQLite database with:
- 3 distinct fictional Indian hotel properties (Jaipur, Goa, Manali)
- 9 room types with distinct capacities and pricing
- Normalized amenities, property/room amenity mappings
- Hotel policies (cancellation, check-in/out, child, pet, extra bed)
- Add-on services with structured pricing types
- 365 days of date-level room inventory (2026-09-01 to 2027-08-31)

Can be executed directly via:
    python -m app.database.seed
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import logging
import sys
from pathlib import Path

# Adjust path if executed directly
current_dir = Path(__file__).resolve().parent
backend_dir = current_dir.parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database.connection import Database, DEFAULT_DB_PATH

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Fixed deterministic reference date for 365-day inventory
REFERENCE_START_DATE = date(2026, 9, 1)
INVENTORY_DAYS = 365


PROPERTIES_DATA = [
    {
        "id": 1,
        "name": "The Grand Heritage Palace",
        "city": "Jaipur",
        "state": "Rajasthan",
        "country": "India",
        "description": "An opulent 5-star heritage palace offering royal Rajasthani hospitality, grand courtyards, hand-painted frescoes, and world-class luxury wellness.",
        "star_rating": 5.0,
        "check_in_time": "14:00",
        "check_out_time": "11:00",
        "address": "Palace Road, Civil Lines, Jaipur, Rajasthan 302006",
    },
    {
        "id": 2,
        "name": "Azure Sands Beach Resort",
        "city": "Goa",
        "state": "Goa",
        "country": "India",
        "description": "A vibrant 4-star beachfront resort in Candolim featuring direct golden sand access, sparkling pools, multi-cuisine dining, and spacious family suites.",
        "star_rating": 4.0,
        "check_in_time": "14:00",
        "check_out_time": "11:00",
        "address": "Candolim Beach Road, Candolim, Bardez, Goa 403515",
    },
    {
        "id": 3,
        "name": "Pinecrest Mountain Lodge",
        "city": "Manali",
        "state": "Himachal Pradesh",
        "country": "India",
        "description": "A cozy, budget-friendly mountain retreat in Old Manali nestled amidst deodar pines and apple orchards, offering panoramic Himalayan valley vistas.",
        "star_rating": 3.5,
        "check_in_time": "12:00",
        "check_out_time": "10:00",
        "address": "Club House Road, Old Manali, Manali, Himachal Pradesh 175131",
    },
]


ROOMS_DATA = [
    # Hotel 1 (Jaipur) - Luxury, smaller capacities
    {
        "id": 1,
        "property_id": 1,
        "name": "Deluxe Heritage Room",
        "description": "Elegantly appointed royal room with traditional jharokha views and marble en-suite bathroom.",
        "max_guests": 2,
        "max_adults": 2,
        "max_children": 1,
        "base_price_per_night": 14000.0,
        "room_size_sqft": 450,
        "bed_type": "King",
        "total_units": 5,
        "status": "active",
    },
    {
        "id": 2,
        "property_id": 1,
        "name": "Royal Courtyard Suite",
        "description": "Spacious suite overlooking the central palace courtyard with private lounge seating and antique decor.",
        "max_guests": 3,
        "max_adults": 3,
        "max_children": 1,
        "base_price_per_night": 22000.0,
        "room_size_sqft": 650,
        "bed_type": "King",
        "total_units": 3,
        "status": "active",
    },
    {
        "id": 3,
        "property_id": 1,
        "name": "Maharaja Presidential Suite",
        "description": "The pinnacle of luxury with two bedrooms, private plunge pool, dining room, and personalized butler service.",
        "max_guests": 4,
        "max_adults": 4,
        "max_children": 2,
        "base_price_per_night": 45000.0,
        "room_size_sqft": 1200,
        "bed_type": "King + Twin",
        "total_units": 2,
        "status": "active",
    },
    # Hotel 2 (Goa) - Mid-range, family friendly, higher capacities
    {
        "id": 4,
        "property_id": 2,
        "name": "Superior Ocean View Room",
        "description": "Contemporary beach room featuring a private sit-out balcony with sweeping Arabian Sea views.",
        "max_guests": 2,
        "max_adults": 2,
        "max_children": 1,
        "base_price_per_night": 6500.0,
        "room_size_sqft": 380,
        "bed_type": "Queen",
        "total_units": 8,
        "status": "active",
    },
    {
        "id": 5,
        "property_id": 2,
        "name": "Family Garden Suite",
        "description": "Generous family suite with dual queen beds, living area, and direct access to lush tropical gardens.",
        "max_guests": 5,
        "max_adults": 4,
        "max_children": 2,
        "base_price_per_night": 11500.0,
        "room_size_sqft": 750,
        "bed_type": "2 Queen Beds",
        "total_units": 4,
        "status": "active",
    },
    {
        "id": 6,
        "property_id": 2,
        "name": "Beachfront Luxury Villa",
        "description": "Exclusive private villa right on the Candolim beachfront with sun terrace and private cabana.",
        "max_guests": 6,
        "max_adults": 6,
        "max_children": 3,
        "base_price_per_night": 18000.0,
        "room_size_sqft": 1100,
        "bed_type": "2 King Beds",
        "total_units": 2,
        "status": "active",
    },
    # Hotel 3 (Manali) - Budget, scenic
    {
        "id": 7,
        "property_id": 3,
        "name": "Cozy Pine Room",
        "description": "Warm wooden-paneled room with pine wood furnishings, heated blankets, and tranquil forest views.",
        "max_guests": 2,
        "max_adults": 2,
        "max_children": 0,
        "base_price_per_night": 2800.0,
        "room_size_sqft": 250,
        "bed_type": "Double",
        "total_units": 6,
        "status": "active",
    },
    {
        "id": 8,
        "property_id": 3,
        "name": "Deluxe Valley View Balcony",
        "description": "Bright room with private wooden balcony capturing uninterrupted snow-capped Himalayan peaks.",
        "max_guests": 3,
        "max_adults": 3,
        "max_children": 1,
        "base_price_per_night": 4200.0,
        "room_size_sqft": 340,
        "bed_type": "Queen + Single",
        "total_units": 4,
        "status": "active",
    },
    {
        "id": 9,
        "property_id": 3,
        "name": "Cedar Attic Family Room",
        "description": "Rustic split-level attic duplex with cedar woodwork, ideal for families or trekking groups.",
        "max_guests": 4,
        "max_adults": 4,
        "max_children": 2,
        "base_price_per_night": 6000.0,
        "room_size_sqft": 500,
        "bed_type": "2 Double Beds",
        "total_units": 3,
        "status": "active",
    },
]


AMENITIES_DATA = [
    {"id": 1, "name": "Free High-Speed Wi-Fi", "category": "general"},
    {"id": 2, "name": "Swimming Pool", "category": "recreation"},
    {"id": 3, "name": "Temperature-Controlled Pool", "category": "recreation"},
    {"id": 4, "name": "Free Parking", "category": "general"},
    {"id": 5, "name": "Valet Parking", "category": "general"},
    {"id": 6, "name": "Air Conditioning", "category": "room"},
    {"id": 7, "name": "Heritage Spa & Wellness", "category": "wellness"},
    {"id": 8, "name": "Multi-Cuisine Restaurant", "category": "dining"},
    {"id": 9, "name": "Royal Dining Room", "category": "dining"},
    {"id": 10, "name": "Direct Beach Access", "category": "location"},
    {"id": 11, "name": "Kids Play Zone", "category": "family"},
    {"id": 12, "name": "Water Sports Desk", "category": "recreation"},
    {"id": 13, "name": "Mountain View", "category": "location"},
    {"id": 14, "name": "Private Balcony", "category": "room"},
    {"id": 15, "name": "Bonfire Area", "category": "recreation"},
    {"id": 16, "name": "In-House Kitchen", "category": "dining"},
    {"id": 17, "name": "Trekking Guide Desk", "category": "recreation"},
    {"id": 18, "name": "24/7 Butler Service", "category": "service"},
    {"id": 19, "name": "Room Heater", "category": "room"},
    {"id": 20, "name": "Sea View", "category": "room"},
]


PROPERTY_AMENITIES_DATA = [
    # Grand Heritage Palace (Jaipur)
    (1, 1), (1, 3), (1, 5), (1, 6), (1, 7), (1, 9), (1, 18),
    # Azure Sands Beach Resort (Goa)
    (2, 1), (2, 2), (2, 4), (2, 6), (2, 8), (2, 10), (2, 11), (2, 12),
    # Pinecrest Mountain Lodge (Manali)
    (3, 1), (3, 4), (3, 13), (3, 15), (3, 16), (3, 17), (3, 19),
]


ROOM_AMENITIES_DATA = [
    # Room 1: Deluxe Heritage Room
    (1, 1), (1, 6),
    # Room 2: Royal Courtyard Suite
    (2, 1), (2, 6), (2, 14),
    # Room 3: Maharaja Presidential Suite
    (3, 1), (3, 6), (3, 14), (3, 18),
    # Room 4: Superior Ocean View Room
    (4, 1), (4, 6), (4, 14), (4, 20),
    # Room 5: Family Garden Suite
    (5, 1), (5, 6), (5, 11),
    # Room 6: Beachfront Luxury Villa
    (6, 1), (6, 6), (6, 10), (6, 14), (6, 20),
    # Room 7: Cozy Pine Room
    (7, 1), (7, 19),
    # Room 8: Deluxe Valley View Balcony
    (8, 1), (8, 13), (8, 14), (8, 19),
    # Room 9: Cedar Attic Family Room
    (9, 1), (9, 13), (9, 19),
]


POLICIES_DATA = [
    # Grand Heritage Palace
    (1, "cancellation", "Free cancellation up to 48 hours before check-in. Cancellations within 48 hours incur a 1-night charge."),
    (1, "check_in", "Check-in time is from 14:00 onwards. Government-issued photo ID required."),
    (1, "check_out", "Check-out time is 11:00. Late check-out subject to availability and fee."),
    (1, "pet", "Strictly no pets allowed on palace premises."),
    (1, "child", "Children up to 5 years stay free using existing bedding. Extra bed charges apply for children aged 6+."),
    # Azure Sands Beach Resort
    (2, "cancellation", "Free cancellation up to 24 hours prior to arrival date."),
    (2, "check_in", "Check-in from 14:00. Early check-in available on request."),
    (2, "check_out", "Check-out is 11:00."),
    (2, "pet", "Small pets (under 10kg) permitted with prior approval and ₹1,000/night sanitation fee."),
    (2, "child", "Children below 6 stay free. Children 6-12 charged at 50% for breakfast buffet."),
    # Pinecrest Mountain Lodge
(3, "cancellation", "Flexible cancellation: full refund if cancelled before 12:00 PM on arrival date."),
    (3, "check_in", "Check-in from 12:00 PM."),
    (3, "check_out", "Check-out by 10:00 AM."),
    (3, "pet", "Pet-friendly property. Well-behaved dogs and cats welcome at no extra fee."),
    (3, "extra_bed", "Extra floor mattress available on request for ₹500/night."),
]


ADD_ONS_DATA = [
    # Grand Heritage Palace (Jaipur)
    (1, 1, "Airport Chauffeur (Roundtrip)", "Private luxury sedan airport pickup and drop-off in Jaipur.", 3500.0, "PER_BOOKING", 1),
    (2, 1, "Royal Thali Dinner Experience", "Authentic 7-course royal Rajasthani banquet at the Royal Dining Room.", 2500.0, "PER_PERSON", 1),
    (3, 1, "Heritage Ayurvedic Spa Ritual", "60-minute therapeutic massage and herbal steam bath.", 4000.0, "PER_PERSON", 1),
    (4, 1, "Palace High Tea", "Traditional evening tea with heritage snacks in the peacock courtyard.", 1200.0, "PER_PERSON", 1),
    # Azure Sands Beach Resort (Goa)
    (5, 2, "Buffet Breakfast", "Daily seaside buffet breakfast featuring Indian, Continental, and Goan specialties.", 600.0, "PER_PERSON_PER_NIGHT", 1),
    (6, 2, "Airport Shuttle (One Way)", "Shared AC shuttle transfer between Dabolim/Mopa airport and resort.", 1200.0, "PER_BOOKING", 1),
    (7, 2, "Extra Rollaway Bed", "Comfortable rollaway bed including fresh linen and pillow.", 1500.0, "PER_NIGHT", 1),
    (8, 2, "Sunset Catamaran Cruise", "2-hour evening sunset catamaran sail with complimentary snacks.", 1500.0, "PER_PERSON", 1),
    # Pinecrest Mountain Lodge (Manali)
    (9, 3, "Home-style Breakfast", "Hearty mountain breakfast with fresh eggs, parathas, local honey, and Himalayan tea.", 300.0, "PER_PERSON_PER_NIGHT", 1),
    (10, 3, "Private Bonfire & BBQ Setup", "Evening outdoor bonfire with barbecue grill, skewers, and wood supply.", 800.0, "PER_BOOKING", 1),
    (11, 3, "Trekking Gear Rental Pack", "Includes two trekking poles, daypack, rain poncho, and headlamp.", 500.0, "PER_PERSON", 1),
    (12, 3, "Premium Room Heater", "Oil-filled radiator heater for extra warmth during chilly Himalayan nights.", 400.0, "PER_NIGHT", 1),
]


def generate_availability_records() -> list[tuple[int, str, int, float | None]]:
    """Generate 365 days of deterministic availability inventory for all 9 rooms.

    Includes explicit sold-out dates and price overrides for robust test scenarios.
    """
    records: list[tuple[int, str, int, float | None]] = []

    for room in ROOMS_DATA:
        room_id = room["id"]
        total_units = room["total_units"]

        for day_offset in range(INVENTORY_DAYS):
            current_date = REFERENCE_START_DATE + timedelta(days=day_offset)
            date_str = current_date.isoformat()
            available = total_units
            price_override = None

            # Test scenario 1: Room 1 (Deluxe Heritage) sold out on 2026-10-15 & 2026-10-16
            if room_id == 1 and current_date in [date(2026, 10, 15), date(2026, 10, 16)]:
                available = 0

            # Test scenario 2: Room 4 (Superior Ocean View) peak season sold out (2026-12-25 to 2026-12-31)
            elif room_id == 4 and date(2026, 12, 25) <= current_date <= date(2026, 12, 31):
                available = 0

            # Test scenario 3: Room 5 (Family Garden Suite) festive price override
            elif room_id == 5 and date(2026, 12, 20) <= current_date <= date(2026, 12, 31):
                price_override = 15000.0

            # Test scenario 4: Periodic simulated bookings (every 10th day room 7 has 1 unit left)
            elif room_id == 7 and day_offset % 10 == 0:
                available = 1

            records.append((room_id, date_str, available, price_override))

    return records


def seed_database(db: Database) -> dict[str, int]:
    """Execute clean database seeding and return record count summary."""
    with db:
        # Recreate tables
        db.create_tables()

        # Clean existing data if any
        db.executescript("""
            DELETE FROM booking_holds;
            DELETE FROM availability;
            DELETE FROM add_ons;
            DELETE FROM policies;
            DELETE FROM room_amenities;
            DELETE FROM property_amenities;
            DELETE FROM amenities;
            DELETE FROM rooms;
            DELETE FROM properties;
        """)

        # 1. Properties
        db.executemany(
            """
            INSERT INTO properties (id, name, city, state, country, description, star_rating, check_in_time, check_out_time, address)
            VALUES (:id, :name, :city, :state, :country, :description, :star_rating, :check_in_time, :check_out_time, :address)
            """,
            PROPERTIES_DATA,
        )

        # 2. Rooms
        db.executemany(
            """
            INSERT INTO rooms (id, property_id, name, description, max_guests, max_adults, max_children, base_price_per_night, room_size_sqft, bed_type, total_units, status)
            VALUES (:id, :property_id, :name, :description, :max_guests, :max_adults, :max_children, :base_price_per_night, :room_size_sqft, :bed_type, :total_units, :status)
            """,
            ROOMS_DATA,
        )

        # 3. Amenities
        db.executemany(
            """
            INSERT INTO amenities (id, name, category)
            VALUES (:id, :name, :category)
            """,
            AMENITIES_DATA,
        )

        # 4. Property Amenities
        db.executemany(
            """
            INSERT INTO property_amenities (property_id, amenity_id)
            VALUES (?, ?)
            """,
            PROPERTY_AMENITIES_DATA,
        )

        # 5. Room Amenities
        db.executemany(
            """
            INSERT INTO room_amenities (room_id, amenity_id)
            VALUES (?, ?)
            """,
            ROOM_AMENITIES_DATA,
        )

        # 6. Policies
        db.executemany(
            """
            INSERT INTO policies (property_id, policy_type, description)
            VALUES (?, ?, ?)
            """,
            POLICIES_DATA,
        )

        # 7. Add-ons
        db.executemany(
            """
            INSERT INTO add_ons (id, property_id, name, description, price, pricing_type, active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ADD_ONS_DATA,
        )

        # 8. Availability
        availability_records = generate_availability_records()
        db.executemany(
            """
            INSERT INTO availability (room_id, date, available_units, price_override)
            VALUES (?, ?, ?, ?)
            """,
            availability_records,
        )

    summary = {
        "properties": len(PROPERTIES_DATA),
        "rooms": len(ROOMS_DATA),
        "amenities": len(AMENITIES_DATA),
        "property_amenities": len(PROPERTY_AMENITIES_DATA),
        "room_amenities": len(ROOM_AMENITIES_DATA),
        "policies": len(POLICIES_DATA),
        "add_ons": len(ADD_ONS_DATA),
        "availability_records": len(availability_records),
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Mehman.io SQLite hotel database.")
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DEFAULT_DB_PATH),
        help=f"Target SQLite database path (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args()

    db = Database(args.db_path)
    logger.info("Seeding database at: %s", db.path)
    summary = seed_database(db)

    logger.info("Successfully seeded database:")
    for table, count in summary.items():
        logger.info("  - %s: %d records", table, count)


if __name__ == "__main__":
    main()
