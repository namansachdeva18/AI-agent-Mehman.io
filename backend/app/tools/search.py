"""Deterministic property search tool.

Queries SQLite directly without calling any LLM.
Supports partial filters: destination, budget, guest capacity, amenities, room preferences, and date-level availability.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from app.database.connection import Database, get_db
from app.errors import AppError, ErrorCode
from app.tools.availability import check_availability
from app.tools.contracts import (
    AvailabilityStatus,
    CheckAvailabilityInput,
    MatchingRoomSummary,
    PropertySearchResult,
    SearchPropertiesInput,
    SearchPropertiesOutput,
)


def search_properties(
    params: SearchPropertiesInput,
    db: Database | None = None,
) -> SearchPropertiesOutput:
    """Search for fictional hotel properties and matching rooms based on structured criteria.

    - Destination matching: case-insensitive against city, state, or hotel name.
    - Amenity matching: strict AND semantics (all requested amenities must be present at property or room level).
    - Budget matching: budget_per_night compared against room nightly rate (including date overrides if dates given).
    - Dates matching: if dates are provided, performs date-level availability check; otherwise sets availability_status = NOT_CHECKED.

    Args:
        params: Search filters.
        db: Optional database connection.

    Returns:
        SearchPropertiesOutput with matching properties and room details.

    Raises:
        AppError: For database errors or invalid search parameters.
    """
    database = db or get_db()
    try:
        with database:
            conditions: list[str] = []
            sql_params: list[Any] = []

            if params.destination:
                dest = f"%{params.destination.strip()}%"
                conditions.append("(p.city LIKE ? OR p.state LIKE ? OR p.name LIKE ?)")
                sql_params.extend([dest, dest, dest])

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            props_query = f"""
                SELECT p.id, p.name, p.city, p.state, p.country, p.description,
                       p.star_rating, p.check_in_time, p.check_out_time, p.address
                FROM properties p
                {where_clause}
                ORDER BY p.star_rating DESC, p.name ASC
            """
            prop_rows = database.execute(props_query, sql_params).fetchall()

            results: list[PropertySearchResult] = []

            for prop in prop_rows:
                prop_id = prop["id"]

                # 1. Fetch property amenities
                prop_amenities_query = """
                    SELECT a.name
                    FROM amenities a
                    JOIN property_amenities pa ON a.id = pa.amenity_id
                    WHERE pa.property_id = ?
                    ORDER BY a.name ASC
                """
                prop_amenity_rows = database.execute(prop_amenities_query, (prop_id,)).fetchall()
                prop_amenity_names = [r["name"] for r in prop_amenity_rows]

                # 2. Fetch rooms for this property
                rooms_query = """
                    SELECT r.id, r.name, r.description, r.max_guests, r.max_adults,
                           r.max_children, r.base_price_per_night, r.room_size_sqft,
                           r.bed_type, r.total_units, r.status
                    FROM rooms r
                    WHERE r.property_id = ? AND r.status = 'active'
                    ORDER BY r.base_price_per_night ASC
                """
                room_rows = database.execute(rooms_query, (prop_id,)).fetchall()

                matching_rooms: list[MatchingRoomSummary] = []
                min_price: float | None = None
                has_available_room = False
                has_checked_dates = params.check_in is not None and params.check_out is not None

                for room in room_rows:
                    room_id = room["id"]
                    base_price = float(room["base_price_per_night"])
                    max_guests = int(room["max_guests"])

                    # Filter by guests capacity
                    if params.guests is not None and max_guests < params.guests:
                        continue

                    # Filter by room preferences (e.g. "Balcony", "Suite", "Ocean", "King")
                    if params.room_preferences:
                        room_text = f"{room['name']} {room['description']}".lower()
                        if not any(pref.lower() in room_text for pref in params.room_preferences):
                            continue

                    # Fetch room-specific amenities
                    room_amenities_query = """
                        SELECT a.name
                        FROM amenities a
                        JOIN room_amenities ra ON a.id = ra.amenity_id
                        WHERE ra.room_id = ?
                        ORDER BY a.name ASC
                    """
                    room_amenity_rows = database.execute(room_amenities_query, (room_id,)).fetchall()
                    room_amenity_names = [r["name"] for r in room_amenity_rows]

                    # Strict AND semantics for requested amenities (case-insensitive)
                    if params.amenities:
                        all_avail = set(a.lower() for a in (prop_amenity_names + room_amenity_names))
                        has_all = all(
                            any(req.strip().lower() == avail or req.strip().lower() in avail for avail in all_avail)
                            for req in params.amenities
                        )
                        if not has_all:
                            continue

                    # Date-level availability check if dates provided
                    room_is_available: bool | None = None
                    effective_nightly_price = base_price

                    if has_checked_dates:
                        avail_out = check_availability(
                            CheckAvailabilityInput(
                                room_id=room_id,
                                check_in=params.check_in,  # type: ignore
                                check_out=params.check_out,  # type: ignore
                                guests=params.guests,
                            ),
                            db=database,
                        )
                        if avail_out.rooms:
                            room_avail_info = avail_out.rooms[0]
                            room_is_available = room_avail_info.available
                            effective_nightly_price = room_avail_info.price_per_night
                            if room_is_available:
                                has_available_room = True
                        else:
                            room_is_available = False

                    # Filter by budget per night
                    if params.budget_per_night is not None and effective_nightly_price > params.budget_per_night:
                        continue

                    matching_rooms.append(
                        MatchingRoomSummary(
                            room_id=room_id,
                            name=room["name"],
                            max_guests=max_guests,
                            base_price_per_night=effective_nightly_price,
                            bed_type=room["bed_type"],
                            room_size_sqft=int(room["room_size_sqft"]),
                            amenities=room_amenity_names,
                            available=room_is_available,
                        )
                    )

                    if min_price is None or effective_nightly_price < min_price:
                        min_price = effective_nightly_price

                # If any criteria were specified and no rooms match, skip property
                has_room_criteria = bool(
                    params.guests or params.budget_per_night or params.room_preferences or params.amenities
                )
                if has_room_criteria and not matching_rooms:
                    continue

                if min_price is None and room_rows:
                    min_price = min(float(r["base_price_per_night"]) for r in room_rows)
                elif min_price is None:
                    min_price = 0.0

                # Determine availability_status
                if not has_checked_dates:
                    status = AvailabilityStatus.NOT_CHECKED
                elif has_available_room:
                    status = AvailabilityStatus.AVAILABLE
                else:
                    status = AvailabilityStatus.UNAVAILABLE

                results.append(
                    PropertySearchResult(
                        property_id=prop_id,
                        property_name=prop["name"],
                        city=prop["city"],
                        state=prop["state"],
                        star_rating=float(prop["star_rating"]),
                        description=prop["description"],
                        check_in_time=prop["check_in_time"],
                        check_out_time=prop["check_out_time"],
                        starting_price_per_night=min_price,
                        matching_rooms=matching_rooms,
                        amenities=prop_amenity_names,
                        availability_status=status,
                    )
                )

            filters_applied = {
                k: v for k, v in params.model_dump().items() if v is not None and v != []
            }

            return SearchPropertiesOutput(
                results=results,
                total_count=len(results),
                filters_applied=filters_applied,
            )

    except sqlite3.Error as e:
        raise AppError(
            code=ErrorCode.DATABASE_ERROR,
            message="Database query failed while searching properties.",
            status_code=500,
            details={"internal_error": str(e)},
        ) from e
