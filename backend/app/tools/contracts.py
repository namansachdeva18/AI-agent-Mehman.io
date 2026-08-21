"""Tool contracts — input and output schemas for all deterministic tools.

All tools operate strictly against SQLite and deterministic Python logic.
No LLM or Gemini integration inside tool execution.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class HoldStatus(str, Enum):
    """Explicit status for booking holds."""

    HELD = "HELD"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    CONFIRMED = "CONFIRMED"


class PricingType(str, Enum):
    """Pricing calculation models for add-on services."""

    PER_NIGHT = "PER_NIGHT"
    PER_BOOKING = "PER_BOOKING"
    PER_PERSON = "PER_PERSON"
    PER_PERSON_PER_NIGHT = "PER_PERSON_PER_NIGHT"


class AvailabilityStatus(str, Enum):
    """Availability status in search results."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    LIMITED = "LIMITED"
    NOT_CHECKED = "NOT_CHECKED"


# ============================================================
# 1. search_properties()
# ============================================================


class SearchPropertiesInput(BaseModel):
    """Input parameters for searching hotel properties."""

    destination: Optional[str] = Field(default=None, description="City or area (e.g. 'Goa', 'Jaipur', 'Manali')")
    check_in: Optional[date] = Field(default=None, description="Check-in date (YYYY-MM-DD)")
    check_out: Optional[date] = Field(default=None, description="Check-out date (YYYY-MM-DD)")
    guests: Optional[int] = Field(default=None, description="Total number of guests", ge=1)
    adults: Optional[int] = Field(default=None, description="Adult guests", ge=1)
    children: Optional[int] = Field(default=None, description="Child guests", ge=0)
    budget_per_night: Optional[float] = Field(default=None, description="Maximum budget per night in INR", gt=0)
    amenities: list[str] = Field(default_factory=list, description="Required amenities (AND logic)")
    room_preferences: list[str] = Field(default_factory=list, description="Keywords for room type")

    @model_validator(mode="after")
    def validate_guests_and_dates(self) -> "SearchPropertiesInput":
        if self.adults is not None or self.children is not None:
            total = (self.adults or 0) + (self.children or 0)
            if self.guests is not None and self.guests != total:
                raise ValueError(f"Total guests ({self.guests}) must equal adults ({self.adults or 0}) + children ({self.children or 0}).")
            if self.guests is None and total > 0:
                self.guests = total

        if (self.check_in is not None and self.check_out is None) or (self.check_in is None and self.check_out is not None):
            raise ValueError("Both check_in and check_out must be provided together.")

        if self.check_in and self.check_out and self.check_in >= self.check_out:
            raise ValueError(f"check_in ({self.check_in}) must be before check_out ({self.check_out}).")

        return self


class MatchingRoomSummary(BaseModel):
    """Room summary within search results."""

    room_id: int
    name: str
    max_guests: int
    base_price_per_night: float
    bed_type: str
    room_size_sqft: int
    amenities: list[str] = Field(default_factory=list)
    available: Optional[bool] = None  # None if dates not checked


class PropertySearchResult(BaseModel):
    """Detailed property information in search results."""

    property_id: int
    property_name: str
    city: str
    state: str
    star_rating: float
    description: str
    check_in_time: str
    check_out_time: str
    starting_price_per_night: float
    matching_rooms: list[MatchingRoomSummary] = Field(default_factory=list)
    amenities: list[str] = Field(default_factory=list)
    availability_status: AvailabilityStatus = AvailabilityStatus.NOT_CHECKED


class SearchPropertiesOutput(BaseModel):
    """Output from property search."""

    results: list[PropertySearchResult] = Field(default_factory=list)
    total_count: int = 0
    filters_applied: dict = Field(default_factory=dict)


# ============================================================
# 2. check_availability()
# ============================================================


class CheckAvailabilityInput(BaseModel):
    """Input for checking room availability."""

    property_id: Optional[int] = Field(default=None, description="Property ID")
    room_id: Optional[int] = Field(default=None, description="Specific Room ID to check")
    check_in: date = Field(description="Check-in date (YYYY-MM-DD)")
    check_out: date = Field(description="Check-out date (YYYY-MM-DD)")
    guests: Optional[int] = Field(default=None, description="Number of guests to validate capacity for", ge=1)
    adults: Optional[int] = Field(default=None, ge=1)
    children: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_dates_and_guests(self) -> "CheckAvailabilityInput":
        if self.adults is not None or self.children is not None:
            total = (self.adults or 0) + (self.children or 0)
            if self.guests is not None and self.guests != total:
                raise ValueError(f"Total guests ({self.guests}) must equal adults ({self.adults or 0}) + children ({self.children or 0}).")
            if self.guests is None and total > 0:
                self.guests = total
        return self


class RoomAvailabilitySummary(BaseModel):
    """Availability result for a single room type."""

    room_id: int
    room_name: str
    max_guests: int
    available: bool
    available_units: int
    price_per_night: float
    unavailability_reason: Optional[str] = None
    unavailable_dates: list[str] = Field(default_factory=list)


class CheckAvailabilityOutput(BaseModel):
    """Output from availability check."""

    property_id: int
    property_name: str
    check_in: date
    check_out: date
    nights: int
    rooms: list[RoomAvailabilitySummary] = Field(default_factory=list)
    all_requested_rooms_available: bool = False


# ============================================================
# 3. get_room_details()
# ============================================================


class GetRoomDetailsInput(BaseModel):
    """Input for retrieving full room details."""

    room_id: int = Field(description="Room ID", ge=1)


class PolicyItem(BaseModel):
    """Hotel policy item."""

    policy_type: str
    description: str


class AddOnItem(BaseModel):
    """Add-on item."""

    id: int
    name: str
    description: str
    price: float
    pricing_type: PricingType


class RoomDetails(BaseModel):
    """Comprehensive room details."""

    room_id: int
    property_id: int
    property_name: str
    city: str
    state: str
    room_name: str
    description: str
    base_price_per_night: float
    max_guests: int
    max_adults: int
    max_children: int
    room_size_sqft: int
    bed_type: str
    total_units: int
    amenities: list[str] = Field(default_factory=list)
    property_amenities: list[str] = Field(default_factory=list)
    policies: list[PolicyItem] = Field(default_factory=list)
    available_add_ons: list[AddOnItem] = Field(default_factory=list)


class GetRoomDetailsOutput(BaseModel):
    """Output from room details retrieval."""

    room: RoomDetails


# ============================================================
# 4. calculate_price()
# ============================================================


class CalculatePriceInput(BaseModel):
    """Input for deterministic price calculation."""

    room_id: int = Field(description="Room ID", ge=1)
    check_in: date = Field(description="Check-in date (YYYY-MM-DD)")
    check_out: date = Field(description="Check-out date (YYYY-MM-DD)")
    guests: int = Field(default=1, description="Total number of guests", ge=1)
    adults: Optional[int] = Field(default=None, ge=1)
    children: Optional[int] = Field(default=None, ge=0)
    selected_add_ons: list[int] = Field(default_factory=list, description="List of Add-on IDs")

    @model_validator(mode="after")
    def validate_guest_breakdown(self) -> "CalculatePriceInput":
        if self.adults is not None or self.children is not None:
            total = (self.adults or 0) + (self.children or 0)
            if self.guests != total:
                self.guests = total
        return self


class NightlyRate(BaseModel):
    """Rate for a single calendar night."""

    date: str
    price: float
    is_override: bool = False


class AddOnCalculation(BaseModel):
    """Itemized breakdown for a selected add-on."""

    add_on_id: int
    name: str
    unit_price: float
    pricing_type: PricingType
    calculation: str
    total_cost: float


class PriceBreakdown(BaseModel):
    """Comprehensive, deterministic price breakdown."""

    room_id: int
    room_name: str
    property_name: str
    check_in: date
    check_out: date
    nights: int
    guests: int
    nightly_rates: list[NightlyRate] = Field(default_factory=list)
    room_total: float
    add_ons_total: float = 0.0
    add_on_items: list[AddOnCalculation] = Field(default_factory=list)
    grand_total: float
    currency: str = "INR"


class CalculatePriceOutput(BaseModel):
    """Output from price calculation."""

    breakdown: PriceBreakdown


# ============================================================
# 5. create_booking_hold() & release_expired_holds()
# ============================================================


class CreateBookingHoldInput(BaseModel):
    """Input for creating a temporary booking hold."""

    room_id: int = Field(description="Room ID", ge=1)
    check_in: date = Field(description="Check-in date (YYYY-MM-DD)")
    check_out: date = Field(description="Check-out date (YYYY-MM-DD)")
    guests: int = Field(default=1, description="Number of guests", ge=1)
    adults: Optional[int] = Field(default=None, ge=1)
    children: Optional[int] = Field(default=None, ge=0)
    guest_name: Optional[str] = Field(default=None, description="Guest name")
    session_id: str = Field(default="", description="Conversation session ID")
    selected_add_ons: list[int] = Field(default_factory=list, description="Selected Add-on IDs")

    @model_validator(mode="after")
    def validate_hold_guests(self) -> "CreateBookingHoldInput":
        if self.adults is not None or self.children is not None:
            total = (self.adults or 0) + (self.children or 0)
            if self.guests != total:
                self.guests = total
        return self


class BookingHold(BaseModel):
    """Details of the created booking hold."""

    hold_id: str
    room_id: int
    room_name: str
    property_name: str
    city: str
    check_in: date
    check_out: date
    nights: int
    guests: int
    guest_name: Optional[str] = None
    total_price: float
    currency: str = "INR"
    status: HoldStatus = HoldStatus.HELD
    expires_at: str  # ISO timestamp
    created_at: str  # ISO timestamp


class CreateBookingHoldOutput(BaseModel):
    """Output from booking hold creation."""

    hold: BookingHold
