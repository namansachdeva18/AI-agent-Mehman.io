"""Deterministic room details retrieval tool.

Queries SQLite directly without calling any LLM.
Retrieves full room specifications, parent property data, amenities, policies, and add-ons.
"""

from __future__ import annotations

from app.database.connection import Database, get_db
from app.errors import AppError, ErrorCode
from app.tools.contracts import (
    AddOnItem,
    GetRoomDetailsInput,
    GetRoomDetailsOutput,
    PolicyItem,
    RoomDetails,
)


def get_room_details(
    params: GetRoomDetailsInput,
    db: Database | None = None,
) -> GetRoomDetailsOutput:
    """Retrieve complete, verified hotel room details from the SQLite database.

    Args:
        params: GetRoomDetailsInput containing room_id.
        db: Optional database connection.

    Returns:
        GetRoomDetailsOutput with complete RoomDetails.

    Raises:
        AppError: With code UNKNOWN_INFORMATION if room does not exist.
    """
    database = db or get_db()
    with database:
        # 1. Fetch room and parent property
        room_row = database.execute(
            """
            SELECT r.id as room_id, r.property_id, r.name as room_name, r.description as room_desc,
                   r.max_guests, r.max_adults, r.max_children, r.base_price_per_night,
                   r.room_size_sqft, r.bed_type, r.total_units, r.status,
                   p.name as property_name, p.city, p.state
            FROM rooms r
            JOIN properties p ON r.property_id = p.id
            WHERE r.id = ?
            """,
            (params.room_id,),
        ).fetchone()

        if not room_row:
            raise AppError(
                code=ErrorCode.UNKNOWN_INFORMATION,
                message=f"Room with ID {params.room_id} does not exist in the hotel database.",
                status_code=404,
            )

        prop_id = room_row["property_id"]

        # 2. Fetch room-specific amenities
        room_amenities_rows = database.execute(
            """
            SELECT a.name
            FROM amenities a
            JOIN room_amenities ra ON a.id = ra.amenity_id
            WHERE ra.room_id = ?
            ORDER BY a.name ASC
            """,
            (params.room_id,),
        ).fetchall()
        room_amenities = [r["name"] for r in room_amenities_rows]

        # 3. Fetch property-level amenities
        prop_amenities_rows = database.execute(
            """
            SELECT a.name
            FROM amenities a
            JOIN property_amenities pa ON a.id = pa.amenity_id
            WHERE pa.property_id = ?
            ORDER BY a.name ASC
            """,
            (prop_id,),
        ).fetchall()
        prop_amenities = [r["name"] for r in prop_amenities_rows]

        # 4. Fetch property policies
        policies_rows = database.execute(
            """
            SELECT policy_type, description
            FROM policies
            WHERE property_id = ?
            ORDER BY policy_type ASC
            """,
            (prop_id,),
        ).fetchall()
        policies = [
            PolicyItem(policy_type=r["policy_type"], description=r["description"])
            for r in policies_rows
        ]

        # 5. Fetch available add-ons
        addons_rows = database.execute(
            """
            SELECT id, name, description, price, pricing_type
            FROM add_ons
            WHERE property_id = ? AND active = 1
            ORDER BY price ASC
            """,
            (prop_id,),
        ).fetchall()
        add_ons = [
            AddOnItem(
                id=r["id"],
                name=r["name"],
                description=r["description"],
                price=float(r["price"]),
                pricing_type=r["pricing_type"],
            )
            for r in addons_rows
        ]

        details = RoomDetails(
            room_id=room_row["room_id"],
            property_id=prop_id,
            property_name=room_row["property_name"],
            city=room_row["city"],
            state=room_row["state"],
            room_name=room_row["room_name"],
            description=room_row["room_desc"],
            base_price_per_night=float(room_row["base_price_per_night"]),
            max_guests=int(room_row["max_guests"]),
            max_adults=int(room_row["max_adults"]),
            max_children=int(room_row["max_children"]),
            room_size_sqft=int(room_row["room_size_sqft"]),
            bed_type=room_row["bed_type"],
            total_units=int(room_row["total_units"]),
            amenities=room_amenities,
            property_amenities=prop_amenities,
            policies=policies,
            available_add_ons=add_ons,
        )

        return GetRoomDetailsOutput(room=details)
