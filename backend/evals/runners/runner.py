"""Evaluation Runner executing golden test cases against the Agent Orchestrator."""

from dataclasses import dataclass
from typing import Any

from app.agent.executor import ToolExecutor
from app.agent.orchestrator import AgentOrchestrator
from app.database.connection import Database
from app.database.seed import seed_database
from app.recommendations.engine import RecommendationEngine
from app.services.conversation import ConversationService
from evals.cases.golden_dataset import GoldenTestCase
from evals.scorers.metrics import CaseScore, score_groundedness, score_state_subset


@dataclass
class EvalSummaryReport:
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate_pct: float
    category_scores: dict[str, float]
    state_accuracy_avg: float
    groundedness_avg: float
    safety_score_avg: float
    case_results: list[CaseScore]


class EvalRunner:
    """Executes evaluation cases in isolated in-memory databases."""

    @staticmethod
    async def run_case(test_case: GoldenTestCase) -> CaseScore:
        test_db = Database(":memory:")
        test_db.connect()
        seed_database(test_db)

        conv_svc = ConversationService(db=test_db)
        executor = ToolExecutor(db=test_db)
        rec_engine = RecommendationEngine(db=test_db)
        orchestrator = AgentOrchestrator(
            llm=None,
            executor=executor,
            conv_service=conv_svc,
            rec_engine=rec_engine,
        )

        conv_id = f"eval-{test_case.case_id.lower()}"
        all_notes: list[str] = []
        turn_state_scores: list[float] = []
        turn_ground_scores: list[float] = []

        try:
            for idx, turn in enumerate(test_case.turns):
                res = await orchestrator.handle_message(conv_id, turn.user_message)
                actual_state = res.booking_state.model_dump()

                # Score state subset for this turn
                s_score, s_notes = score_state_subset(actual_state, turn.expected_state_subset)
                turn_state_scores.append(s_score)
                all_notes.extend(s_notes)

                # Score groundedness for this turn
                g_score, g_notes = score_groundedness(res.message, turn.required_terms, turn.forbidden_terms)
                turn_ground_scores.append(g_score)
                all_notes.extend(g_notes)

                if turn.expected_booking_success is True:
                    if not res.booking_state.hold_id:
                        all_notes.append("Expected booking hold to be created, but hold_id is None")

            # Validate expected final state if specified
            if test_case.expected_final_state:
                final_conv = conv_svc.get_conversation(conv_id)
                final_state = final_conv.booking.model_dump()
                f_score, f_notes = score_state_subset(final_state, test_case.expected_final_state)
                turn_state_scores.append(f_score)
                all_notes.extend(f_notes)

            avg_state = sum(turn_state_scores) / len(turn_state_scores) if turn_state_scores else 1.0
            avg_ground = sum(turn_ground_scores) / len(turn_ground_scores) if turn_ground_scores else 1.0
            safety_score = 1.0 if not any("forbidden" in n.lower() or "safety" in n.lower() for n in all_notes) else 0.0

            passed = (avg_state >= 0.99) and (avg_ground >= 0.99) and (safety_score == 1.0) and (len(all_notes) == 0)

            return CaseScore(
                case_id=test_case.case_id,
                category=test_case.category,
                passed=passed,
                state_accuracy=avg_state,
                groundedness=avg_ground,
                safety_score=safety_score,
                notes=all_notes,
            )

        finally:
            test_db.close()

    @classmethod
    async def run_all(cls, cases: list[GoldenTestCase]) -> EvalSummaryReport:
        results: list[CaseScore] = []
        for case in cases:
            res = await cls.run_case(case)
            results.append(res)

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_pct = (passed / total * 100.0) if total > 0 else 0.0

        categories: dict[str, list[CaseScore]] = {}
        for r in results:
            categories.setdefault(r.category, []).append(r)

        cat_scores: dict[str, float] = {}
        for cat, r_list in categories.items():
            cat_scores[cat] = (sum(1 for r in r_list if r.passed) / len(r_list)) * 100.0

        return EvalSummaryReport(
            total_cases=total,
            passed_cases=passed,
            failed_cases=failed,
            pass_rate_pct=pass_pct,
            category_scores=cat_scores,
            state_accuracy_avg=sum(r.state_accuracy for r in results) / total if total > 0 else 0.0,
            groundedness_avg=sum(r.groundedness for r in results) / total if total > 0 else 0.0,
            safety_score_avg=sum(r.safety_score for r in results) / total if total > 0 else 0.0,
            case_results=results,
        )
