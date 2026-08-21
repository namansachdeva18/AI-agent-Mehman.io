"""Property and Room Comparison Service.

Produces structured, factual side-by-side comparison tables
for 2 or 3 hotels/rooms without hallucinating subjective facts.
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.connection import Database
from app.recommendations.models import ComparisonItem, PropertyComparisonResult
from app.tools.contracts import CalculatePriceInput, GetRoomDetailsInput
from app.tools.pricing import calculate_price
from app.tools.room_details import get_room_details

logger = logging.getLogger(__name__)


def compare_rooms(
    room_ids: list[int],
    check_in: Any = None,
    check_out: Any = None,
    guests: int = 2,
    db: Database | None = None,
) -> PropertyComparisonResult:
    """Generate structured side-by-side comparison of 2 or 3 rooms."""
    items: list[ComparisonItem] = []
    key_differences: list[str] = []

    for rid in room_ids[:3]:
        try:
            rm_out = get_room_details(GetRoomDetailsInput(room_id=rid), db=db)
            rm = rm_out.room

            star_rating = 4.5
            if db:
                row = db.execute(
                    "SELECT star_rating FROM properties WHERE id = ?", (rm.property_id,)
                ).fetchone()
                if row:
                    star_rating = float(row["star_rating"])

            # Calculate stay total if dates are provided
            total_p = None
            if check_in and check_out:
                try:
                    p_out = calculate_price(
                        CalculatePriceInput(
                            room_id=rid,
                            check_in=check_in,
                            check_out=check_out,
                            guests=guests,
                        ),
                        db=db,
                    )
                    total_p = p_out.breakdown.grand_total
                except Exception:
                    total_p = None

            policy_texts: list[str] = []
            for p in rm.policies:
                ptype = getattr(p, "policy_type", "") or (p.get("policy_type") if isinstance(p, dict) else "")
                pdesc = getattr(p, "description", "") or (p.get("description") if isinstance(p, dict) else "")
                policy_texts.append(f"{ptype}: {pdesc}")

            add_on_dicts: list[dict[str, Any]] = []
            for a in rm.available_add_ons:
                if hasattr(a, "model_dump"):
                    add_on_dicts.append(a.model_dump())
                elif isinstance(a, dict):
                    add_on_dicts.append(a)

            items.append(
                ComparisonItem(
                    property_id=rm.property_id,
                    property_name=rm.property_name,
                    city=rm.city,
                    star_rating=star_rating,
                    room_id=rm.room_id,
                    room_name=rm.room_name,
                    nightly_price=rm.base_price_per_night,
                    total_price=total_p,
                    max_guests=rm.max_guests,
                    room_size_sqft=rm.room_size_sqft,
                    bed_type=rm.bed_type,
                    amenities=rm.amenities + rm.property_amenities,
                    policies=policy_texts,
                    available_add_ons=add_on_dicts,
                )
            )
        except Exception as e:
            logger.warning(f"Failed to fetch details for room_id {rid}: {e}")

    # Build key factual differences
    if len(items) >= 2:
        cheapest_item = min(items, key=lambda it: it.nightly_price)
        priciest_item = max(items, key=lambda it: it.nightly_price)

        if cheapest_item.room_id != priciest_item.room_id:
            diff_amount = priciest_item.nightly_price - cheapest_item.nightly_price
            key_differences.append(
                f"Price Difference: {cheapest_item.room_name} is ₹{diff_amount:,.2f}/night more affordable than {priciest_item.room_name}."
            )

        stars = {it.star_rating for it in items}
        if len(stars) > 1:
            key_differences.append(
                "Star Ratings: " + ", ".join(f"{it.property_name} ({it.star_rating}★)" for it in items)
            )

        caps = {it.max_guests for it in items}
        if len(caps) > 1:
            key_differences.append(
                "Capacities: " + ", ".join(f"{it.room_name} ({it.max_guests} guests)" for it in items)
            )

    summary = (
        f"Compared {len(items)} room options across "
        + ", ".join({it.property_name for it in items})
        + "."
    )

    return PropertyComparisonResult(
        properties=items,
        key_differences=key_differences,
        comparison_summary=summary,
    )
