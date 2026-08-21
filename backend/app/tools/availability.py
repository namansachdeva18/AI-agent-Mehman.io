"""Deterministic availability checking tool.

Queries SQLite directly without calling any LLM.
Validates date ordering, guest capacity, and date-level inventory with hotel-style checkout-exclusive semantics.
"""

from __future__ import annotations

from datetime import date, timedelta
import sqlite3
from typing import Any

from app.database.connection import Database, get_db
from app.errors import AppError, ErrorCode
from app.tools.contracts import (
    CheckAvailabilityInput,
    CheckAvailabilityOutput,
    RoomAvailabilitySummary,
)


def check_availability(
    params: CheckAvailabilityInput,
    db: Database | None = None,
) -> CheckAvailabilityOutput:
    """Check room availability across a date range for a property or specific room type.

    Hotel Date Semantics:
    - check_in is inclusive.
    - check_out is exclusive.
    - Stay nights = (check_out - check_in).days.
    - Every night must have available_units >= 1.

    Args:
        params: CheckAvailabilityInput with dates, property_id or room_id, and guests.
        db: Optional database connection.

    Returns:
        CheckAvailabilityOutput with room-by-room availability and night count.

    Raises:
        AppError: For invalid dates, nonexistent rooms/properties, or database errors.
    """
    if params.check_in >= params.check_out:
        raise AppError(
            code=ErrorCode.INVALID_DATES,
            message=f"Check-in date ({params.check_in}) must be before check-out date ({params.check_out}).",
            status_code=400,
        )

    stay_nights = (params.check_out - params.check_in).days
    if stay_nights <= 0:
        raise AppError(
            code=ErrorCode.INVALID_DATES,
            message="Stay must be at least 1 night.",
            status_code=400,
        )

    if params.guests is not None and params.guests < 1:
        raise AppError(
            code=ErrorCode.INVALID_REQUEST,
            message="Guest count must be at least 1.",
            status_code=400,
        )

    if params.property_id is None and params.room_id is None:
        raise AppError(
            code=ErrorCode.INVALID_REQUEST,
            message="Either property_id or room_id must be provided to check availability.",
            status_code=400,
        )

    database = db or get_db()
    try:
        with database:
            if params.room_id is not None:
                room_row = database.execute(
                    """
                    SELECT r.id, r.property_id, r.name, r.max_guests, r.base_price_per_night,
                           p.name as property_name
                    FROM rooms r
                    JOIN properties p ON r.property_id = p.id
                    WHERE r.id = ? AND r.status = 'active'
                    """,
                    (params.room_id,),
                ).fetchone()

                if not room_row:
                    raise AppError(
                        code=ErrorCode.UNKNOWN_INFORMATION,
                        message=f"Room with ID {params.room_id} does not exist.",
                        status_code=404,
                    )

                prop_id = room_row["property_id"]
                prop_name = room_row["property_name"]
                target_rooms = [room_row]
            else:
                prop_row = database.execute(
                    "SELECT id, name FROM properties WHERE id = ?",
                    (params.property_id,),
                ).fetchone()

                if not prop_row:
                    raise AppError(
                        code=ErrorCode.UNKNOWN_INFORMATION,
                        message=f"Property with ID {params.property_id} does not exist.",
                        status_code=404,
                    )

                prop_id = prop_row["id"]
                prop_name = prop_row["name"]

                target_rooms = database.execute(
                    """
                    SELECT id, property_id, name, max_guests, base_price_per_night
                    FROM rooms
                    WHERE property_id = ? AND status = 'active'
                    ORDER BY base_price_per_night ASC
                    """,
                    (prop_id,),
                ).fetchall()

            stay_dates = [
                (params.check_in + timedelta(days=i)).isoformat()
                for i in range(stay_nights)
            ]

            rooms_summary: list[RoomAvailabilitySummary] = []
            any_room_available = False

            for room in target_rooms:
                r_id = room["id"]
                r_name = room["name"]
                r_max_guests = int(room["max_guests"])
                base_price = float(room["base_price_per_night"])

                # 1. Capacity validation
                if params.guests is not None and params.guests > r_max_guests:
                    rooms_summary.append(
                        RoomAvailabilitySummary(
                            room_id=r_id,
                            room_name=r_name,
                            max_guests=r_max_guests,
                            available=False,
                            available_units=0,
                            price_per_night=base_price,
                            unavailability_reason="capacity_exceeded",
                            unavailable_dates=[],
                        )
                    )
                    continue

                # 2. Query availability inventory for each night of the stay
                placeholders = ",".join("?" for _ in stay_dates)
                avail_rows = database.execute(
                    f"""
                    SELECT date, available_units, price_override
                    FROM availability
                    WHERE room_id = ? AND date IN ({placeholders})
                    ORDER BY date ASC
                    """,
                    [r_id] + stay_dates,
                ).fetchall()

                avail_by_date = {row["date"]: row for row in avail_rows}

                is_available = True
                min_units_available = 999
                effective_nightly_price = base_price
                failed_dates: list[str] = []
                unavail_reason: str | None = None

                for date_str in stay_dates:
                    if date_str not in avail_by_date:
                        is_available = False
                        min_units_available = 0
                        failed_dates.append(date_str)
                        if not unavail_reason:
                            unavail_reason = "outside_inventory_range"
                        continue

                    row = avail_by_date[date_str]
                    units = int(row["available_units"])
                    if units <= 0:
                        is_available = False
                        min_units_available = 0
                        failed_dates.append(date_str)
                        if not unavail_reason:
                            unavail_reason = "sold_out"
                        continue

                    min_units_available = min(min_units_available, units)
                    if row["price_override"] is not None:
                        effective_nightly_price = float(row["price_override"])

                if min_units_available == 999:
                    min_units_available = 0

                if is_available:
                    any_room_available = True

                rooms_summary.append(
                    RoomAvailabilitySummary(
                        room_id=r_id,
                        room_name=r_name,
                        max_guests=r_max_guests,
                        available=is_available,
                        available_units=min_units_available if is_available else 0,
                        price_per_night=effective_nightly_price,
                        unavailability_reason=unavail_reason,
                        unavailable_dates=failed_dates,
                    )
                )

            return CheckAvailabilityOutput(
                property_id=prop_id,
                property_name=prop_name,
                check_in=params.check_in,
                check_out=params.check_out,
                nights=stay_nights,
                rooms=rooms_summary,
                all_requested_rooms_available=any_room_available,
            )

    except sqlite3.Error as e:
        raise AppError(
            code=ErrorCode.DATABASE_ERROR,
            message="Database query failed while checking room availability.",
            status_code=500,
            details={"internal_error": str(e)},
        ) from e
