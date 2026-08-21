"""Deterministic booking hold creation and inventory management tool.

Handles:
- Atomic inventory decrement upon hold creation
- 15-minute hold expiry tracking
- Deterministic expired hold release and inventory restoration
- Concurrency and rollback safety
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import sqlite3
import uuid

from app.database.connection import Database, get_db
from app.errors import AppError, ErrorCode
from app.tools.availability import check_availability
from app.tools.contracts import (
    BookingHold,
    CalculatePriceInput,
    CheckAvailabilityInput,
    CreateBookingHoldInput,
    CreateBookingHoldOutput,
    HoldStatus,
)
from app.tools.pricing import calculate_price


def create_booking_hold(
    params: CreateBookingHoldInput,
    db: Database | None = None,
) -> CreateBookingHoldOutput:
    """Create a temporary reservation hold and atomically decrement room inventory.

    Transactional sequence:
    1. Validate date order and guest count.
    2. Check continuous availability across all requested stay nights.
    3. Calculate deterministic price.
    4. ATOMIC TRANSACTION:
       - Decrement available_units by 1 for each stay night WHERE available_units > 0.
       - If any night fails (0 rows updated), rollback and raise UNAVAILABLE_ROOM.
       - Insert record into booking_holds table with status 'HELD' and 15-minute expiry.
       - Commit.

    Args:
        params: CreateBookingHoldInput with room_id, dates, guests, name, add_ons.
        db: Optional database connection.

    Returns:
        CreateBookingHoldOutput with confirmed hold details.

    Raises:
        AppError: For invalid dates, capacity issues, unavailable rooms, or database errors.
    """
    database = db or get_db()
    # Always release expired holds first so fresh inventory is immediately accessible
    release_expired_holds(db=database)



    # 1. Check availability & capacity
    avail_input = CheckAvailabilityInput(
        room_id=params.room_id,
        check_in=params.check_in,
        check_out=params.check_out,
        guests=params.guests,
    )
    avail_result = check_availability(avail_input, db=database)

    room_avail = next(
        (r for r in avail_result.rooms if r.room_id == params.room_id), None
    )

    if not room_avail or not room_avail.available:
        reason = room_avail.unavailability_reason if room_avail else "unavailable"
        if reason == "capacity_exceeded":
            raise AppError(
                code=ErrorCode.CAPACITY_ERROR,
                message=f"Room capacity exceeded for {params.guests} guests.",
                status_code=400,
            )
        raise AppError(
            code=ErrorCode.UNAVAILABLE_ROOM,
            message=(
                f"Room is not available between {params.check_in} and {params.check_out} "
                f"(Reason: {reason})."
            ),
            status_code=409,
        )

    # 2. Calculate deterministic price
    price_input = CalculatePriceInput(
        room_id=params.room_id,
        check_in=params.check_in,
        check_out=params.check_out,
        guests=params.guests,
        selected_add_ons=params.selected_add_ons,
    )
    price_result = calculate_price(price_input, db=database)
    breakdown = price_result.breakdown

    # 3. Generate unique hold ID and timestamps
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=15)
    hold_code = f"HOLD-{uuid.uuid4().hex[:8].upper()}"

    now_iso = now.isoformat()
    expires_iso = expires_at.isoformat()

    stay_nights = (params.check_out - params.check_in).days
    stay_dates = [
        (params.check_in + timedelta(days=i)).isoformat()
        for i in range(stay_nights)
    ]

    # 4. Atomic inventory decrement and hold creation
    try:
        with database:
            # Check room info
            prop_row = database.execute(
                """
                SELECT p.name as property_name, p.city
                FROM properties p
                JOIN rooms r ON p.id = r.property_id
                WHERE r.id = ?
                """,
                (params.room_id,),
            ).fetchone()

            property_name = prop_row["property_name"] if prop_row else "Hotel"
            city = prop_row["city"] if prop_row else "India"

            # Decrement inventory for each night atomically
            for date_str in stay_dates:
                cursor = database.execute(
                    """
                    UPDATE availability
                    SET available_units = available_units - 1
                    WHERE room_id = ? AND date = ? AND available_units > 0
                    """,
                    (params.room_id, date_str),
                )
                if cursor.rowcount == 0:
                    # Concurrency conflict or inventory exhausted: rollback automatically via with block
                    raise AppError(
                        code=ErrorCode.UNAVAILABLE_ROOM,
                        message=f"Room inventory exhausted for date {date_str} during hold reservation.",
                        status_code=409,
                    )

            # Insert hold record
            database.execute(
                """
                INSERT INTO booking_holds (
                    id, room_id, session_id, guest_name, check_in, check_out,
                    guests, total_price, currency, status, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hold_code,
                    params.room_id,
                    params.session_id or f"sess-{uuid.uuid4().hex[:6]}",
                    params.guest_name,
                    params.check_in.isoformat(),
                    params.check_out.isoformat(),
                    params.guests,
                    breakdown.grand_total,
                    "INR",
                    HoldStatus.HELD.value,
                    expires_iso,
                    now_iso,
                ),
            )

    except sqlite3.Error as e:
        raise AppError(
            code=ErrorCode.DATABASE_ERROR,
            message="Database transaction failed while creating booking hold.",
            status_code=500,
            details={"internal_error": str(e)},
        ) from e

    hold_details = BookingHold(
        hold_id=hold_code,
        room_id=params.room_id,
        room_name=breakdown.room_name,
        property_name=property_name,
        city=city,
        check_in=params.check_in,
        check_out=params.check_out,
        nights=breakdown.nights,
        guests=params.guests,
        guest_name=params.guest_name,
        total_price=breakdown.grand_total,
        currency="INR",
        status=HoldStatus.HELD,
        expires_at=expires_iso,
        created_at=now_iso,
    )

    return CreateBookingHoldOutput(hold=hold_details)


def release_expired_holds(
    as_of: datetime | None = None,
    db: Database | None = None,
) -> int:
    """Find all expired HELD reservations, restore room inventory, and mark them EXPIRED.

    Deterministic function that can be called anytime.

    Args:
        as_of: Reference expiration cutoff (defaults to UTC now).
        db: Optional database connection.

    Returns:
        Number of expired holds released.
    """
    if isinstance(as_of, Database):
        db = as_of
        as_of = None

    cutoff = as_of or datetime.now(UTC)
    cutoff_iso = cutoff.isoformat()

    database = db or get_db()
    released_count = 0

    try:
        with database:
            # Find all expired holds
            expired_rows = database.execute(
                """
                SELECT id, room_id, check_in, check_out
                FROM booking_holds
                WHERE status = 'HELD' AND expires_at <= ?
                """,
                (cutoff_iso,),
            ).fetchall()

            for row in expired_rows:
                hold_id = row["id"]
                room_id = int(row["room_id"])
                c_in = date.fromisoformat(row["check_in"])
                c_out = date.fromisoformat(row["check_out"])

                stay_nights = (c_out - c_in).days
                stay_dates = [
                    (c_in + timedelta(days=i)).isoformat()
                    for i in range(stay_nights)
                ]

                # Restore inventory for each night of the expired stay
                for date_str in stay_dates:
                    database.execute(
                        """
                        UPDATE availability
                        SET available_units = available_units + 1
                        WHERE room_id = ? AND date = ?
                        """,
                        (room_id, date_str),
                    )

                # Mark hold record as EXPIRED
                database.execute(
                    "UPDATE booking_holds SET status = ? WHERE id = ?",
                    (HoldStatus.EXPIRED.value, hold_id),
                )
                released_count += 1

            database.commit()

        return released_count

    except sqlite3.Error as e:
        raise AppError(
            code=ErrorCode.DATABASE_ERROR,
            message="Database transaction failed while releasing expired holds.",
            status_code=500,
            details={"internal_error": str(e)},
        ) from e


def cancel_booking_hold(
    hold_id: str,
    db: Database | None = None,
) -> bool:
    """Cancel an active booking hold and restore inventory."""
    database = db or get_db()
    try:
        with database:
            hold = database.execute(
                "SELECT id, room_id, check_in, check_out, status FROM booking_holds WHERE id = ?",
                (hold_id,),
            ).fetchone()

            if not hold:
                raise AppError(
                    code=ErrorCode.UNKNOWN_INFORMATION,
                    message=f"Booking hold '{hold_id}' not found.",
                    status_code=404,
                )

            if hold["status"] != HoldStatus.HELD.value:
                return False  # Already expired or cancelled

            room_id = int(hold["room_id"])
            c_in = date.fromisoformat(hold["check_in"])
            c_out = date.fromisoformat(hold["check_out"])
            stay_nights = (c_out - c_in).days

            stay_dates = [
                (c_in + timedelta(days=i)).isoformat()
                for i in range(stay_nights)
            ]

            for date_str in stay_dates:
                database.execute(
                    """
                    UPDATE availability
                    SET available_units = available_units + 1
                    WHERE room_id = ? AND date = ?
                    """,
                    (room_id, date_str),
                )

            database.execute(
                "UPDATE booking_holds SET status = ? WHERE id = ?",
                (HoldStatus.CANCELLED.value, hold_id),
            )
            database.commit()
            return True

    except sqlite3.Error as e:
        raise AppError(
            code=ErrorCode.DATABASE_ERROR,
            message="Database transaction failed while cancelling booking hold.",
            status_code=500,
            details={"internal_error": str(e)},
        ) from e
