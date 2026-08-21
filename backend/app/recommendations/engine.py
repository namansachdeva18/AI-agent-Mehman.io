"""Deterministic Recommendation and Ranking Engine.

Executes a 2-stage recommendation pipeline:
1. Hard Constraint Filtering (destination, availability, capacity, max budget ceiling)
2. Deterministic Normalized Scoring (quality, value, capacity fit, amenity & preference match)
3. Multi-strategy weighting (BEST_MATCH, CHEAPEST, BEST_VALUE, LUXURY, FAMILY)
4. Deterministic tie-breaking and relaxed alternative suggestions
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.connection import Database
from app.recommendations.models import (
    BudgetMode,
    MatchType,
    RankingStrategy,
    RecommendationCandidate,
    RecommendationResult,
    ScoreBreakdown,
    TravelerType,
)
from app.tools.contracts import PropertySearchResult, SearchPropertiesInput
from app.tools.pricing import calculate_price
from app.tools.search import search_properties

logger = logging.getLogger(__name__)

# Deterministic amenity normalization & alias dictionary
AMENITY_ALIASES: dict[str, list[str]] = {
    "pool": ["temperature-controlled pool", "swimming pool", "pool", "kids pool"],
    "swimming pool": ["temperature-controlled pool", "swimming pool", "pool", "kids pool"],
    "beach": ["direct beach access", "beachfront", "beach", "sea view", "beach access"],
    "beachfront": ["direct beach access", "beachfront", "sea view"],
    "spa": ["heritage spa & wellness", "ayurvedic spa", "spa", "wellness"],
    "balcony": ["private balcony", "valley view balcony", "balcony"],
    "mountain view": ["mountain views", "valley view balcony", "deluxe valley view balcony"],
    "butler": ["butler service", "24/7 royal butler service", "butler"],
    "kids": ["kids play zone", "kids pool", "family room"],
    "family": ["kids play zone", "kids pool", "family garden suite", "cedar attic family room", "bonfire area"],
}

# Strategy weight configurations
STRATEGY_WEIGHTS: dict[RankingStrategy, dict[str, float]] = {
    RankingStrategy.BEST_MATCH: {
        "preference": 0.35,
        "value": 0.25,
        "quality": 0.15,
        "capacity": 0.15,
        "amenity": 0.10,
    },
    RankingStrategy.BEST_VALUE: {
        "preference": 0.10,
        "value": 0.50,
        "quality": 0.20,
        "capacity": 0.10,
        "amenity": 0.10,
    },
    RankingStrategy.LUXURY: {
        "preference": 0.35,
        "value": 0.05,
        "quality": 0.40,
        "capacity": 0.10,
        "amenity": 0.10,
    },
    RankingStrategy.FAMILY: {
        "preference": 0.35,
        "value": 0.20,
        "quality": 0.10,
        "capacity": 0.25,
        "amenity": 0.10,
    },
    RankingStrategy.CHEAPEST: {
        "preference": 0.05,
        "value": 0.70,
        "quality": 0.10,
        "capacity": 0.10,
        "amenity": 0.05,
    },
    RankingStrategy.PRICE_LOW_TO_HIGH: {
        "preference": 0.05,
        "value": 0.70,
        "quality": 0.10,
        "capacity": 0.10,
        "amenity": 0.05,
    },
}


class RecommendationEngine:
    """Deterministic recommendation engine for ranking hotel room options."""

    def __init__(self, db: Database | None = None) -> None:
        self._db = db

    def rank_candidates(
        self,
        search_results: list[PropertySearchResult],
        guests: int = 2,
        budget_per_night: float | None = None,
        budget_mode: BudgetMode = BudgetMode.MAX,
        preferred_amenities: list[str] | None = None,
        traveler_type: TravelerType = TravelerType.STANDARD,
        strategy: RankingStrategy = RankingStrategy.BEST_MATCH,
        top_n: int = 3,
        check_in: Any = None,
        check_out: Any = None,
        db: Database | None = None,
    ) -> RecommendationResult:
        """Filter candidates by hard constraints and score remaining options deterministically."""
        target_db = db or self._db
        prefs = preferred_amenities or []
        candidates: list[RecommendationCandidate] = []
        alternative_candidates: list[RecommendationCandidate] = []
        total_evaluated = 0

        # Stage 1: Flatten search results into room candidates & evaluate hard constraints
        for prop in search_results:
            prop_amenities = [a.lower() for a in prop.amenities]
            for rm in prop.matching_rooms:
                total_evaluated += 1
                room_amenities = [a.lower() for a in rm.amenities]
                all_avail_amenities = set(prop_amenities + room_amenities)

                # Hard Constraint 1: Capacity
                if rm.max_guests < guests:
                    # Collect as possible alternative if gap is small
                    continue

                # Hard Constraint 2: Availability (if availability was checked)
                if rm.available is False:
                    continue

                # Hard Constraint 3: Budget Ceiling (only if MAX mode)
                if budget_per_night is not None and budget_mode == BudgetMode.MAX:
                    if rm.base_price_per_night > budget_per_night:
                        # Collect as alternative suggestion
                        alt_cand = self._score_candidate(
                            prop=prop,
                            rm=rm,
                            all_amenities=all_avail_amenities,
                            guests=guests,
                            budget_per_night=budget_per_night,
                            budget_mode=budget_mode,
                            preferred_amenities=prefs,
                            traveler_type=traveler_type,
                            strategy=strategy,
                            match_type=MatchType.ALTERNATIVE,
                            check_in=check_in,
                            check_out=check_out,
                            db=target_db,
                        )
                        alternative_candidates.append(alt_cand)
                        continue

                # Candidate qualifies for Stage 2 Scoring
                cand = self._score_candidate(
                    prop=prop,
                    rm=rm,
                    all_amenities=all_avail_amenities,
                    guests=guests,
                    budget_per_night=budget_per_night,
                    budget_mode=budget_mode,
                    preferred_amenities=prefs,
                    traveler_type=traveler_type,
                    strategy=strategy,
                    match_type=MatchType.EXACT_MATCH,
                    check_in=check_in,
                    check_out=check_out,
                    db=target_db,
                )
                candidates.append(cand)

        # Stage 2: Sort candidates using deterministic tie-breaking
        sorted_candidates = self._sort_candidates(candidates, strategy=strategy)
        top_candidates = sorted_candidates[:top_n]

        # If zero exact matches, provide top alternatives if available
        alternatives_used = False
        if not top_candidates and alternative_candidates:
            sorted_alts = self._sort_candidates(alternative_candidates, strategy=strategy)
            top_candidates = sorted_alts[:top_n]
            alternatives_used = True

        best_cand = top_candidates[0] if top_candidates else None

        return RecommendationResult(
            candidates=top_candidates,
            recommended_candidate=best_cand,
            ranking_strategy=strategy,
            applied_constraints={
                "guests": guests,
                "budget_per_night": budget_per_night,
                "budget_mode": budget_mode.value,
            },
            applied_preferences={
                "preferred_amenities": prefs,
                "traveler_type": traveler_type.value,
            },
            alternatives_available=alternatives_used,
            total_candidates_evaluated=total_evaluated,
            total_candidates_qualified=len(candidates),
        )

    def _score_candidate(
        self,
        prop: PropertySearchResult,
        rm: Any,
        all_amenities: set[str],
        guests: int,
        budget_per_night: float | None,
        budget_mode: BudgetMode,
        preferred_amenities: list[str],
        traveler_type: TravelerType,
        strategy: RankingStrategy,
        match_type: MatchType,
        check_in: Any = None,
        check_out: Any = None,
        db: Database | None = None,
    ) -> RecommendationCandidate:
        """Compute normalized 0.0 to 1.0 scores across all 5 dimensions."""
        # 1. Quality Score (Star rating & room size normalized)
        star_norm = min(1.0, max(0.0, prop.star_rating / 5.0))
        size_norm = min(1.0, max(0.0, rm.room_size_sqft / 1000.0))
        quality_score = 0.7 * star_norm + 0.3 * size_norm

        # 2. Capacity Fit Score (Perfect 1.0 when max_guests == guests; penalty for excess wasted beds)
        excess_beds = max(0, rm.max_guests - guests)
        capacity_fit = max(0.0, min(1.0, 1.0 - 0.1 * excess_beds))

        # 3. Value Score (Quality and room size relative to price)
        price = rm.base_price_per_night
        baseline = 10000.0
        price_factor = max(0.2, price / baseline)
        raw_val = (0.5 * star_norm + 0.5 * size_norm) / price_factor
        value_score = max(0.0, min(1.0, raw_val * 0.8))

        # For CHEAPEST strategy, prioritize pure lower nightly rate
        if strategy in (RankingStrategy.CHEAPEST, RankingStrategy.PRICE_LOW_TO_HIGH):
            value_score = max(0.0, min(1.0, 1.0 - (price / 50000.0)))

        # 4. Amenity Match Score
        matched_amenities: list[str] = []
        unmatched_prefs: list[str] = []
        if preferred_amenities:
            match_count = 0
            for pref in preferred_amenities:
                pref_lower = pref.strip().lower()
                aliases = AMENITY_ALIASES.get(pref_lower, [pref_lower])
                if any(alias in avail or avail in alias for alias in aliases for avail in all_amenities):
                    match_count += 1
                    matched_amenities.append(pref)
                else:
                    unmatched_prefs.append(pref)
            amenity_match = match_count / len(preferred_amenities)
        else:
            amenity_match = 1.0

        # 5. Preference Match Score (Traveler type & lifestyle tags)
        pref_score = 0.5  # Neutral baseline
        if traveler_type == TravelerType.FAMILY:
            family_tags = ["kids play zone", "kids pool", "family room", "swimming pool", "bonfire"]
            tag_hits = sum(1 for t in family_tags if any(t in a for a in all_amenities))
            pref_score = min(1.0, 0.4 + 0.15 * tag_hits)
            if "family" in rm.name.lower() or "family" in prop.property_name.lower():
                pref_score = min(1.0, pref_score + 0.2)
        elif traveler_type == TravelerType.LUXURY:
            luxury_tags = ["heritage spa & wellness", "butler service", "temperature-controlled pool"]
            tag_hits = sum(1 for t in luxury_tags if any(t in a for a in all_amenities))
            pref_score = min(1.0, 0.3 + 0.2 * tag_hits + 0.3 * (prop.star_rating / 5.0))
        elif traveler_type == TravelerType.BUDGET:
            pref_score = max(0.0, min(1.0, 1.0 - (price / 20000.0)))
        else:
            # Standard: combine amenity match and budget fit
            pref_score = amenity_match

        # Budget Target modifier (if TARGET mode)
        if budget_per_night is not None and budget_mode == BudgetMode.TARGET:
            diff = abs(price - budget_per_night)
            budget_proximity = max(0.0, min(1.0, 1.0 - (diff / budget_per_night)))
            pref_score = 0.6 * pref_score + 0.4 * budget_proximity

        # Calculate Weighted Final Score
        w = STRATEGY_WEIGHTS.get(strategy, STRATEGY_WEIGHTS[RankingStrategy.BEST_MATCH])
        final_score = (
            w["preference"] * pref_score
            + w["value"] * value_score
            + w["quality"] * quality_score
            + w["capacity"] * capacity_fit
            + w["amenity"] * amenity_match
        )
        final_score = round(max(0.0, min(1.0, final_score)), 4)

        score_breakdown = ScoreBreakdown(
            preference_match=round(pref_score, 3),
            value_score=round(value_score, 3),
            quality_score=round(quality_score, 3),
            capacity_fit=round(capacity_fit, 3),
            amenity_match=round(amenity_match, 3),
            final_score=final_score,
        )

        # Generate deterministic recommendation reason
        reason = self._build_recommendation_reason(
            prop, rm, strategy, score_breakdown, match_type, budget_per_night
        )

        # Compute total stay price if check_in and check_out are provided
        total_p = None
        if check_in and check_out:
            try:
                from app.tools.contracts import CalculatePriceInput
                p_out = calculate_price(
                    CalculatePriceInput(
                        room_id=rm.room_id,
                        check_in=check_in,
                        check_out=check_out,
                        guests=guests,
                    ),
                    db=db,
                )
                total_p = p_out.breakdown.grand_total
            except Exception:
                total_p = None

        return RecommendationCandidate(
            property_id=prop.property_id,
            property_name=prop.property_name,
            city=prop.city,
            star_rating=prop.star_rating,
            room_id=rm.room_id,
            room_name=rm.name,
            room_size_sqft=rm.room_size_sqft,
            bed_type=rm.bed_type,
            nightly_price=rm.base_price_per_night,
            total_price=total_p,
            max_guests=rm.max_guests,
            available=rm.available if rm.available is not None else True,
            matched_amenities=matched_amenities,
            unmatched_preferences=unmatched_prefs,
            match_type=match_type,
            score_breakdown=score_breakdown,
            recommendation_reason=reason,
        )

    def _sort_candidates(
        self,
        candidates: list[RecommendationCandidate],
        strategy: RankingStrategy,
    ) -> list[RecommendationCandidate]:
        """Deterministic tie-breaking sort:
        1. Final Score (descending) [or nightly_price ascending for CHEAPEST]
        2. Preference Match Score (descending)
        3. Nightly Price (ascending)
        4. Star Rating (descending)
        5. Stable (property_id, room_id) (ascending)
        """
        if strategy in (RankingStrategy.CHEAPEST, RankingStrategy.PRICE_LOW_TO_HIGH):
            return sorted(
                candidates,
                key=lambda c: (
                    c.nightly_price,
                    -c.score_breakdown.preference_match,
                    -c.star_rating,
                    c.property_id,
                    c.room_id,
                ),
            )

        return sorted(
            candidates,
            key=lambda c: (
                -c.score_breakdown.final_score,
                -c.score_breakdown.preference_match,
                c.nightly_price,
                -c.star_rating,
                c.property_id,
                c.room_id,
            ),
        )

    def _build_recommendation_reason(
        self,
        prop: PropertySearchResult,
        rm: Any,
        strategy: RankingStrategy,
        scores: ScoreBreakdown,
        match_type: MatchType,
        budget: float | None,
    ) -> str:
        """Construct deterministic explanation sentence for the candidate."""
        if match_type == MatchType.ALTERNATIVE:
            if budget and rm.base_price_per_night > budget:
                return (
                    f"Closest available alternative at ₹{rm.base_price_per_night:,.2f}/night "
                    f"(exceeds budget by ₹{rm.base_price_per_night - budget:,.2f})."
                )
            return f"Alternative option fitting your guest requirements at {prop.property_name}."

        if strategy == RankingStrategy.CHEAPEST:
            return f"Lowest priced option at ₹{rm.base_price_per_night:,.2f}/night accommodating up to {rm.max_guests} guests."
        if strategy == RankingStrategy.BEST_VALUE:
            return (
                f"Top value rating ({scores.value_score:.2f}) offering {prop.star_rating}★ quality "
                f"and {rm.room_size_sqft} sq ft space at ₹{rm.base_price_per_night:,.2f}/night."
            )
        if strategy == RankingStrategy.LUXURY:
            return f"Premier {prop.star_rating}★ luxury experience with {rm.bed_type} bedding and signature amenities."
        if strategy == RankingStrategy.FAMILY:
            return f"Ideal family layout accommodating {rm.max_guests} guests with dedicated resort recreation."

        return (
            f"Strongest overall match ({int(scores.final_score * 100)}% match) balancing "
            f"{prop.star_rating}★ quality, capacity fit, and ₹{rm.base_price_per_night:,.2f}/night rate."
        )


# Default singleton instance
recommendation_engine = RecommendationEngine()
