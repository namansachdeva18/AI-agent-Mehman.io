"""Recommendation and comparison package for Mehman.io."""

from app.recommendations.comparison import compare_rooms
from app.recommendations.engine import RecommendationEngine, recommendation_engine
from app.recommendations.models import (
    BudgetMode,
    ComparisonItem,
    MatchType,
    PropertyComparisonResult,
    RankingStrategy,
    RecommendationCandidate,
    RecommendationResult,
    ScoreBreakdown,
    TravelerType,
)

__all__ = [
    "BudgetMode",
    "ComparisonItem",
    "MatchType",
    "PropertyComparisonResult",
    "RankingStrategy",
    "RecommendationCandidate",
    "RecommendationEngine",
    "RecommendationResult",
    "ScoreBreakdown",
    "TravelerType",
    "compare_rooms",
    "recommendation_engine",
]
