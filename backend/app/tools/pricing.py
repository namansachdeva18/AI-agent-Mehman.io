"""Deterministic price calculation tool.

Calculates exact stay pricing using Python application logic and database rates.
Gemini is NEVER called for pricing.
"""

from __future__ import annotations

from datetime import date, timedelta
import sqlite3
from typing import Any

from app.database.connection import Database, get_db
from app.errors import AppError, ErrorCode
from app.tools.contracts import (
    AddOnCalculation,
    CalculatePriceInput,
    CalculatePriceOutput,
    NightlyRate,
    PriceBreakdown,
    PricingType,
)


def calculate_price(
    params: CalculatePriceInput,
    db: Database | None = None,
) -> CalculatePriceOutput:
    """Deterministically calculate the total stay cost including nightly rates and add-on services.

    Formulas:
    - Nights = (check_out - check_in).days
    - Room Total = sum(effective_nightly_rates for each night)
    - Add-on calculations:
        - PER_NIGHT: unit_price × nights
        - PER_BOOKING: unit_price
        - PER_PERSON: unit_price × guests
        - PER_PERSON_PER_NIGHT: unit_price × guests × nights
    - Grand Total = Room Total + Add-ons Total (Zero arbitrary taxes)

    Args:
        params: CalculatePriceInput containing room_id, dates, guests, and add_on_ids.
        db: Optional database connection.

    Returns:
        CalculatePriceOutput with complete PriceBreakdown.

    Raises:
        AppError: For invalid dates, capacity conflicts, nonexistent rooms, or invalid add-ons.
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

    if params.guests < 1:
        raise AppError(
            code=ErrorCode.INVALID_REQUEST,
            message="Guest count must be at least 1.",
            status_code=400,
        )

    database = db or get_db()
    try:
        with database:
            # 1. Fetch room details
            room_row = database.execute(
                """
                SELECT r.id, r.property_id, r.name as room_name, r.max_guests,
                       r.base_price_per_night, p.name as property_name
                FROM rooms r
                JOIN properties p ON r.property_id = p.id
                WHERE r.id = ?
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
            room_name = room_row["room_name"]
            prop_name = room_row["property_name"]
            max_guests = int(room_row["max_guests"])
            base_price = float(room_row["base_price_per_night"])

            # 2. Capacity validation
            if params.guests > max_guests:
                raise AppError(
                    code=ErrorCode.CAPACITY_ERROR,
                    message=(
                        f"Requested {params.guests} guests, but {room_name} "
                        f"has a maximum capacity of {max_guests} guests."
                    ),
                    status_code=400,
                    details={"requested_guests": params.guests, "max_guests": max_guests},
                )

            # 3. Calculate nightly rates with date-specific overrides
            stay_dates = [
                (params.check_in + timedelta(days=i)).isoformat()
                for i in range(stay_nights)
            ]
            placeholders = ",".join("?" for _ in stay_dates)
            avail_rows = database.execute(
                f"""
                SELECT date, price_override
                FROM availability
                WHERE room_id = ? AND date IN ({placeholders})
                """,
                [params.room_id] + stay_dates,
            ).fetchall()

            overrides_by_date = {
                row["date"]: row["price_override"]
                for row in avail_rows
                if row["price_override"] is not None
            }

            nightly_rates: list[NightlyRate] = []
            room_total = 0.0

            for date_str in stay_dates:
                override = overrides_by_date.get(date_str)
                if override is not None:
                    rate = float(override)
                    is_override = True
                else:
                    rate = base_price
                    is_override = False

                nightly_rates.append(
                    NightlyRate(date=date_str, price=rate, is_override=is_override)
                )
                room_total += rate

            # 4. Calculate Add-ons
            add_on_items: list[AddOnCalculation] = []
            add_ons_total = 0.0

            if params.selected_add_ons:
                addon_placeholders = ",".join("?" for _ in params.selected_add_ons)
                addon_rows = database.execute(
                    f"""
                    SELECT id, property_id, name, price, pricing_type, active
                    FROM add_ons
                    WHERE id IN ({addon_placeholders})
                    """,
                    params.selected_add_ons,
                ).fetchall()

                addon_dict = {row["id"]: row for row in addon_rows}

                for addon_id in params.selected_add_ons:
                    if addon_id not in addon_dict:
                        raise AppError(
                            code=ErrorCode.INVALID_REQUEST,
                            message=f"Add-on with ID {addon_id} does not exist.",
                            status_code=400,
                        )

                    row = addon_dict[addon_id]
                    if row["property_id"] != prop_id:
                        raise AppError(
                            code=ErrorCode.INVALID_REQUEST,
                            message=f"Add-on '{row['name']}' belongs to another property and cannot be selected.",
                            status_code=400,
                        )

                    if not bool(row["active"]):
                        raise AppError(
                            code=ErrorCode.INVALID_REQUEST,
                            message=f"Add-on '{row['name']}' is currently inactive.",
                            status_code=400,
                        )

                    unit_price = float(row["price"])
                    pricing_type_str = row["pricing_type"]
                    pricing_type = PricingType(pricing_type_str)

                    # Deterministic mathematical formulas
                    if pricing_type == PricingType.PER_NIGHT:
                        cost = unit_price * stay_nights
                        calc_desc = f"₹{unit_price:,.0f} × {stay_nights} night(s)"
                    elif pricing_type == PricingType.PER_BOOKING:
                        cost = unit_price
                        calc_desc = f"₹{unit_price:,.0f} flat per booking"
                    elif pricing_type == PricingType.PER_PERSON:
                        cost = unit_price * params.guests
                        calc_desc = f"₹{unit_price:,.0f} × {params.guests} guest(s)"
                    elif pricing_type == PricingType.PER_PERSON_PER_NIGHT:
                        cost = unit_price * params.guests * stay_nights
                        calc_desc = f"₹{unit_price:,.0f} × {params.guests} guest(s) × {stay_nights} night(s)"
                    else:
                        cost = unit_price
                        calc_desc = f"₹{unit_price:,.0f}"

                    add_ons_total += cost
                    add_on_items.append(
                        AddOnCalculation(
                            add_on_id=addon_id,
                            name=row["name"],
                            unit_price=unit_price,
                            pricing_type=pricing_type,
                            calculation=calc_desc,
                            total_cost=cost,
                        )
                    )

            grand_total = room_total + add_ons_total

            breakdown = PriceBreakdown(
                room_id=params.room_id,
                room_name=room_name,
                property_name=prop_name,
                check_in=params.check_in,
                check_out=params.check_out,
                nights=stay_nights,
                guests=params.guests,
                nightly_rates=nightly_rates,
                room_total=room_total,
                add_ons_total=add_ons_total,
                add_on_items=add_on_items,
                grand_total=grand_total,
                currency="INR",
            )

            return CalculatePriceOutput(breakdown=breakdown)

    except sqlite3.Error as e:
        raise AppError(
            code=ErrorCode.DATABASE_ERROR,
            message="Database query failed while calculating price.",
            status_code=500,
            details={"internal_error": str(e)},
        ) from e
