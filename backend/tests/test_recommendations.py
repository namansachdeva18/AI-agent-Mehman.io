"""Comprehensive unit tests for the Deterministic Recommendation Engine and Comparison Service.

Covers:
- Hard constraint filtering (capacity, availability, budget ceiling, destination)
- Budget modes (MAX vs TARGET)
- 6 Ranking strategies (BEST_MATCH, CHEAPEST, BEST_VALUE, LUXURY, FAMILY, PRICE_LOW_TO_HIGH)
- Deterministic scoring normalization (0.0 to 1.0)
- Deterministic tie-breaking and ordering stability
- Amenity normalization & alias matching
- No-match behavior and relaxed alternative suggestions
- Side-by-side property comparison
"""

from datetime import date
import pytest

from app.database.connection import Database
from app.database.seed import seed_database
from app.recommendations.comparison import compare_rooms
from app.recommendations.engine import RecommendationEngine, recommendation_engine
from app.recommendations.models import (
    BudgetMode,
    MatchType,
    RankingStrategy,
    TravelerType,
)
from app.tools.contracts import SearchPropertiesInput
from app.tools.search import search_properties


@pytest.fixture
def db():
    """Create an isolated, seeded in-memory SQLite database for testing."""
    test_db = Database(":memory:")
    test_db.connect()
    seed_database(test_db)
    yield test_db
    test_db.close()


class TestRecommendationEngineUnit:
    """Unit tests for the RecommendationEngine."""

    def test_empty_search_results_returns_empty_result(self, db):
        """Empty candidate pool returns 0 candidates safely."""
        res = recommendation_engine.rank_candidates(
            search_results=[],
            guests=2,
            db=db,
        )
        assert res.candidates == []
        assert res.recommended_candidate is None
        assert res.total_candidates_qualified == 0

    def test_hard_capacity_filter_eliminates_small_rooms(self, db):
        """Searching for 5 guests in Goa must strictly exclude 2-guest rooms (Room 4)."""
        search_out = search_properties(SearchPropertiesInput(destination="Goa"), db=db)
        res = recommendation_engine.rank_candidates(
            search_results=search_out.results,
            guests=5,
            db=db,
        )
        assert len(res.candidates) >= 1
        # Room 4 (max 2) must be excluded; Room 5 (max 5) and Room 6 (max 6) must be included
        room_ids = [c.room_id for c in res.candidates]
        assert 4 not in room_ids
        assert 5 in room_ids or 6 in room_ids
        assert all(c.max_guests >= 5 for c in res.candidates)

    def test_hard_budget_max_filter_eliminates_expensive_rooms(self, db):
        """Hard budget MAX = ₹10,000 must exclude rooms > ₹10,000."""
        search_out = search_properties(SearchPropertiesInput(destination="Goa"), db=db)
        res = recommendation_engine.rank_candidates(
            search_results=search_out.results,
            guests=2,
            budget_per_night=10000.0,
            budget_mode=BudgetMode.MAX,
            db=db,
        )
        # Room 4 is ₹6,500 (included). Room 5 (₹11.5k) and Room 6 (₹18k) excluded from exact matches.
        assert len(res.candidates) == 1
        assert res.candidates[0].room_id == 4
        assert res.candidates[0].nightly_price <= 10000.0

    def test_soft_budget_target_mode_includes_rooms_above_target(self, db):
        """Soft budget TARGET = ₹10,000 should score and rank rooms near target without excluding them."""
        search_out = search_properties(SearchPropertiesInput(destination="Goa"), db=db)
        res = recommendation_engine.rank_candidates(
            search_results=search_out.results,
            guests=2,
            budget_per_night=10000.0,
            budget_mode=BudgetMode.TARGET,
            db=db,
        )
        # All 3 rooms are qualified, scored based on proximity
        assert len(res.candidates) == 3
        assert res.total_candidates_qualified == 3

    def test_cheapest_strategy_ranks_by_lowest_price(self, db):
        """CHEAPEST strategy must place the lowest nightly rate at Rank 1."""
        search_out = search_properties(SearchPropertiesInput(destination="Manali"), db=db)
        res = recommendation_engine.rank_candidates(
            search_results=search_out.results,
            guests=2,
            strategy=RankingStrategy.CHEAPEST,
            db=db,
        )
        assert len(res.candidates) == 3
        # Room 7 is ₹2,800, Room 8 is ₹4,200, Room 9 is ₹6,000
        assert res.candidates[0].room_id == 7
        assert res.candidates[0].nightly_price == 2800.0
        assert res.candidates[1].nightly_price <= res.candidates[2].nightly_price

    def test_luxury_strategy_ranks_by_star_rating_and_suite_quality(self, db):
        """LUXURY strategy in Jaipur must rank Maharaja Presidential Suite (5.0★, ₹45k) at top."""
        search_out = search_properties(SearchPropertiesInput(destination="Jaipur"), db=db)
        res = recommendation_engine.rank_candidates(
            search_results=search_out.results,
            guests=2,
            traveler_type=TravelerType.LUXURY,
            strategy=RankingStrategy.LUXURY,
            db=db,
        )
        assert len(res.candidates) == 3
        # Maharaja Suite (Room 3) has butler service, spa, 1200 sq ft -> Rank 1
        assert res.candidates[0].room_id == 3
        assert res.candidates[0].star_rating == 5.0

    def test_family_strategy_prioritizes_family_rooms_and_amenities(self, db):
        """FAMILY strategy in Goa must rank Family Garden Suite (Room 5) as top recommendation."""
        search_out = search_properties(SearchPropertiesInput(destination="Goa"), db=db)
        res = recommendation_engine.rank_candidates(
            search_results=search_out.results,
            guests=4,
            traveler_type=TravelerType.FAMILY,
            strategy=RankingStrategy.FAMILY,
            db=db,
        )
        assert len(res.candidates) >= 1
        assert res.candidates[0].room_id == 5
        assert "family" in res.candidates[0].room_name.lower()

    def test_best_value_strategy_balances_quality_and_rate(self, db):
        """BEST_VALUE strategy evaluates value score rather than simply lowest rate."""
        search_out = search_properties(SearchPropertiesInput(destination="Manali"), db=db)
        res = recommendation_engine.rank_candidates(
            search_results=search_out.results,
            guests=2,
            strategy=RankingStrategy.BEST_VALUE,
            db=db,
        )
        assert len(res.candidates) >= 1
        # Top candidate has high value score breakdown
        top = res.candidates[0]
        assert top.score_breakdown.value_score > 0.5

    def test_score_normalization_in_valid_range(self, db):
        """All score components must strictly lie within [0.0, 1.0]."""
        search_out = search_properties(SearchPropertiesInput(destination="Jaipur"), db=db)
        res = recommendation_engine.rank_candidates(
            search_results=search_out.results,
            guests=2,
            db=db,
        )
        for c in res.candidates:
            b = c.score_breakdown
            assert 0.0 <= b.preference_match <= 1.0
            assert 0.0 <= b.value_score <= 1.0
            assert 0.0 <= b.quality_score <= 1.0
            assert 0.0 <= b.capacity_fit <= 1.0
            assert 0.0 <= b.amenity_match <= 1.0
            assert 0.0 <= b.final_score <= 1.0

    def test_amenity_alias_matching(self, db):
        """User requesting 'pool' and 'beach' matches 'Temperature-Controlled Pool' and 'Direct Beach Access'."""
        search_out = search_properties(SearchPropertiesInput(destination="Goa"), db=db)
        res = recommendation_engine.rank_candidates(
            search_results=search_out.results,
            guests=2,
            preferred_amenities=["pool", "beach"],
            db=db,
        )
        top = res.candidates[0]
        assert "pool" in top.matched_amenities
        assert "beach" in top.matched_amenities
        assert top.score_breakdown.amenity_match == 1.0

    def test_deterministic_tie_breaking_order_stability(self, db):
        """Executing ranking multiple times on identical input produces identical ordered outputs."""
        search_out = search_properties(SearchPropertiesInput(destination="Jaipur"), db=db)
        r1 = recommendation_engine.rank_candidates(search_results=search_out.results, guests=2, db=db)
        r2 = recommendation_engine.rank_candidates(search_results=search_out.results, guests=2, db=db)

        order1 = [(c.property_id, c.room_id, c.score_breakdown.final_score) for c in r1.candidates]
        order2 = [(c.property_id, c.room_id, c.score_breakdown.final_score) for c in r2.candidates]
        assert order1 == order2

    def test_no_exact_match_returns_alternative_suggestion(self, db):
        """When budget ceiling is ₹2,000 in Manali (cheapest is ₹2,800), engine returns ALTERNATIVE candidate."""
        search_out = search_properties(SearchPropertiesInput(destination="Manali"), db=db)
        res = recommendation_engine.rank_candidates(
            search_results=search_out.results,
            guests=2,
            budget_per_night=2000.0,
            budget_mode=BudgetMode.MAX,
            db=db,
        )
        assert res.total_candidates_qualified == 0
        assert res.alternatives_available is True
        assert len(res.candidates) >= 1
        assert res.candidates[0].match_type == MatchType.ALTERNATIVE
        assert "exceeds budget" in res.candidates[0].recommendation_reason


class TestComparisonServiceUnit:
    """Unit tests for side-by-side room comparison."""

    def test_compare_two_rooms_generates_differences(self, db):
        """Comparing Room 4 (Goa Ocean View) and Room 5 (Goa Family Suite)."""
        cmp_res = compare_rooms(
            room_ids=[4, 5],
            check_in=date(2026, 9, 10),
            check_out=date(2026, 9, 13),
            guests=2,
            db=db,
        )
        assert len(cmp_res.properties) == 2
        p1, p2 = cmp_res.properties[0], cmp_res.properties[1]

        assert p1.room_name == "Superior Ocean View Room"
        assert p2.room_name == "Family Garden Suite"
        assert p1.nightly_price == 6500.0
        assert p2.nightly_price == 11500.0
        assert p1.total_price == 19500.0
        assert p2.total_price == 34500.0

        assert len(cmp_res.key_differences) >= 1
        assert "Price Difference" in cmp_res.key_differences[0]
