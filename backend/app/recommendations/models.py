"""Domain models and schemas for the Deterministic Recommendation Engine.

Defines:
- Ranking strategies (BEST_MATCH, CHEAPEST, BEST_VALUE, LUXURY, FAMILY, etc.)
- Budget modes (MAX, TARGET, FLEXIBLE)
- Traveler profiles / use cases (FAMILY, COUPLE, LUXURY, BUDGET, etc.)
- Score breakdowns (normalized 0.0 to 1.0 components)
- Candidate and result models
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class RankingStrategy(str, Enum):
    """Supported deterministic ranking and recommendation strategies."""

    BEST_MATCH = "BEST_MATCH"
    CHEAPEST = "CHEAPEST"
    BEST_VALUE = "BEST_VALUE"
    LUXURY = "LUXURY"
    FAMILY = "FAMILY"
    PRICE_LOW_TO_HIGH = "PRICE_LOW_TO_HIGH"


class BudgetMode(str, Enum):
    """Semantics of the user's budget statement."""

    MAX = "MAX"  # "under ₹10,000", "max ₹10,000" -> Hard constraint
    TARGET = "TARGET"  # "around ₹10,000", "my budget is ₹10,000" -> Soft preference
    FLEXIBLE = "FLEXIBLE"  # No strict ceiling


class TravelerType(str, Enum):
    """Inferred or explicit traveler profile."""

    FAMILY = "FAMILY"
    COUPLE = "COUPLE"
    LUXURY = "LUXURY"
    BUDGET = "BUDGET"
    BUSINESS = "BUSINESS"
    GROUP = "GROUP"
    SOLO = "SOLO"
    STANDARD = "STANDARD"


class ScoreBreakdown(BaseModel):
    """Itemized score breakdown with normalized 0.0 to 1.0 components."""

    preference_match: float = Field(ge=0.0, le=1.0, description="Match score for user preferences")
    value_score: float = Field(ge=0.0, le=1.0, description="Normalized price-to-quality/size value score")
    quality_score: float = Field(ge=0.0, le=1.0, description="Normalized hotel star rating and tier quality")
    capacity_fit: float = Field(ge=0.0, le=1.0, description="Fit score for guest count without excessive wasted beds")
    amenity_match: float = Field(ge=0.0, le=1.0, description="Fraction of requested amenities satisfied")
    final_score: float = Field(ge=0.0, le=1.0, description="Weighted composite score")


class MatchType(str, Enum):
    """Type of candidate recommendation match."""

    EXACT_MATCH = "EXACT_MATCH"
    ALTERNATIVE = "ALTERNATIVE"


class RecommendationCandidate(BaseModel):
    """A scored and ranked hotel room candidate."""

    property_id: int
    property_name: str
    city: str
    star_rating: float
    room_id: int
    room_name: str
    room_size_sqft: int
    bed_type: str
    nightly_price: float
    total_price: Optional[float] = None
    max_guests: int
    available: bool = True
    matched_amenities: list[str] = Field(default_factory=list)
    unmatched_preferences: list[str] = Field(default_factory=list)
    match_type: MatchType = MatchType.EXACT_MATCH
    score_breakdown: ScoreBreakdown
    recommendation_reason: str = ""


class RecommendationResult(BaseModel):
    """Complete output produced by the Deterministic Recommendation Engine."""

    candidates: list[RecommendationCandidate] = Field(default_factory=list)
    recommended_candidate: Optional[RecommendationCandidate] = None
    ranking_strategy: RankingStrategy = RankingStrategy.BEST_MATCH
    applied_constraints: dict[str, Any] = Field(default_factory=dict)
    applied_preferences: dict[str, Any] = Field(default_factory=dict)
    alternatives_available: bool = False
    total_candidates_evaluated: int = 0
    total_candidates_qualified: int = 0


class ComparisonItem(BaseModel):
    """Side-by-side comparison item for a single room candidate."""

    property_id: int
    property_name: str
    city: str
    star_rating: float
    room_id: int
    room_name: str
    nightly_price: float
    total_price: Optional[float] = None
    max_guests: int
    room_size_sqft: int
    bed_type: str
    amenities: list[str] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)
    available_add_ons: list[dict[str, Any]] = Field(default_factory=list)


class PropertyComparisonResult(BaseModel):
    """Structured side-by-side comparison table."""

    properties: list[ComparisonItem] = Field(default_factory=list)
    key_differences: list[str] = Field(default_factory=list)
    comparison_summary: str = ""
