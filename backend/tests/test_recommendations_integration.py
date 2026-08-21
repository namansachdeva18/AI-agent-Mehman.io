"""Integration tests for Recommendation & Pricing Intelligence with AgentOrchestrator.

Tests:
1. Conversational recommendation flow with ranking strategy selection.
2. Side-by-side comparison query flow.
3. Stale recommendation invalidation upon destination change.
4. Fresh availability check before booking hold creation.
5. End-to-end multi-turn journey with recommendation, comparison, pricing, and booking hold.
"""

from datetime import date
import pytest

from app.agent.executor import ToolExecutor
from app.agent.orchestrator import AgentOrchestrator
from app.agent.schemas import NextAction
from app.database.connection import Database
from app.database.seed import seed_database
from app.recommendations.engine import RecommendationEngine
from app.services.conversation import ConversationService


@pytest.fixture
def db():
    """Create an isolated, seeded in-memory SQLite database for testing."""
    test_db = Database(":memory:")
    test_db.connect()
    seed_database(test_db)
    yield test_db
    test_db.close()


@pytest.fixture
def orchestrator(db):
    """Create an AgentOrchestrator backed by the isolated test database."""
    conv_svc = ConversationService(db=db)
    executor = ToolExecutor(db=db)
    rec_engine = RecommendationEngine(db=db)
    return AgentOrchestrator(llm=None, executor=executor, conv_service=conv_svc, rec_engine=rec_engine)


class TestRecommendationIntegration:
    """Integration test suite for agent recommendations and comparisons."""

    @pytest.mark.anyio
    async def test_cheapest_recommendation_query(self, orchestrator):
        """User asks 'Which is the cheapest hotel in Manali?' -> returns Pinecrest Cozy Pine Room."""
        conv_id = "conv-rec-cheap"
        res = await orchestrator.handle_message(
            conv_id,
            "What is the cheapest hotel in Manali from 10th to 13th September for 2 people?",
        )
        assert res.next_action == NextAction.RECOMMEND_PROPERTIES
        assert "Pinecrest Mountain Lodge" in res.message
        assert "Cozy Pine Room" in res.message
        assert "₹2,800.00/night" in res.message

    @pytest.mark.anyio
    async def test_family_recommendation_query(self, orchestrator):
        """User asks for family recommendation in Goa for 5 people -> returns Family Garden Suite."""
        conv_id = "conv-rec-fam"
        res = await orchestrator.handle_message(
            conv_id,
            "Recommend a family hotel in Goa from 10th to 13th September for 5 people",
        )
        assert res.next_action == NextAction.RECOMMEND_PROPERTIES
        assert "Family Garden Suite" in res.message
        assert "Azure Sands Beach Resort" in res.message

    @pytest.mark.anyio
    async def test_comparison_query_flow(self, orchestrator):
        """User asks 'Compare the rooms in Goa' -> returns structured side-by-side comparison."""
        conv_id = "conv-rec-compare"
        await orchestrator.handle_message(conv_id, "I need a stay in Goa from 10th to 13th September for 2 guests")
        res = await orchestrator.handle_message(conv_id, "Compare the rooms available in Goa")

        assert res.next_action == NextAction.COMPARE_PROPERTIES
        assert "Room Comparison" in res.message
        assert "Superior Ocean View Room" in res.message
        assert "Family Garden Suite" in res.message
        assert "Price Difference" in res.message

    @pytest.mark.anyio
    async def test_stale_recommendation_invalidation(self, orchestrator):
        """When destination changes from Goa to Jaipur, previous Goa room selections are cleared."""
        conv_id = "conv-rec-stale"
        # 1. Recommend in Goa
        await orchestrator.handle_message(conv_id, "Recommend a luxury room in Goa from 10th to 13th September for 2 people")
        await orchestrator.handle_message(conv_id, "Show me the Beachfront Luxury Villa")

        b1 = orchestrator._conv_service.get_conversation(conv_id).booking
        assert b1.destination == "Goa"
        assert b1.selected_room_id == 6

        # 2. Change destination to Jaipur
        res2 = await orchestrator.handle_message(conv_id, "Actually, let's switch to Jaipur")
        b2 = res2.booking_state
        assert b2.destination == "Jaipur"
        assert b2.selected_room_id is None
        assert b2.selected_property_id is None

    @pytest.mark.anyio
    async def test_fresh_availability_revalidation_before_hold(self, orchestrator, db):
        """If a room becomes unavailable between recommendation and booking, hold creation safely fails."""
        conv_id = "conv-rec-soldout"
        # 1. Search & Select Room 4 in Goa
        await orchestrator.handle_message(conv_id, "Hotel in Goa from 10th to 12th September for 2 people")
        await orchestrator.handle_message(conv_id, "Tell me about Superior Ocean View Room")

        # 2. Simulate concurrent sell-out on database: set available_units = 0
        with db:
            db.execute("UPDATE availability SET available_units = 0 WHERE room_id = 4 AND date = '2026-09-10'")
            db.commit()

        # 3. User attempts booking: must re-validate fresh availability and fail gracefully
        hold_res = await orchestrator.handle_message(conv_id, "Book it for Amit")
        assert "no longer available" in hold_res.message.lower() or "could not create" in hold_res.message.lower()
        assert hold_res.booking_state.hold_id is None
