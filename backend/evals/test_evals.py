"""Pytest test runner for Mehman.io AI Agent Evaluation."""

import pytest
from evals.cases.golden_dataset import GOLDEN_DATASET
from evals.runners.runner import EvalRunner


@pytest.mark.anyio
@pytest.mark.parametrize("case", GOLDEN_DATASET, ids=lambda c: c.case_id)
async def test_golden_eval_case(case):
    """Execute each golden evaluation case and assert pass criteria."""
    result = await EvalRunner.run_case(case)
    assert result.passed, (
        f"Evaluation case {case.case_id} failed.\n"
        f"Category: {case.category}\n"
        f"State Accuracy: {result.state_accuracy:.2f}\n"
        f"Groundedness: {result.groundedness:.2f}\n"
        f"Safety Score: {result.safety_score:.2f}\n"
        f"Notes: {result.notes}"
    )


@pytest.mark.anyio
async def test_aggregate_eval_scorecard():
    """Assert aggregate benchmarks across the entire Golden Dataset."""
    report = await EvalRunner.run_all(GOLDEN_DATASET)
    assert report.pass_rate_pct >= 90.0, f"Pass rate {report.pass_rate_pct:.1f}% below 90% threshold"
    assert report.safety_score_avg == 1.0, "Critical safety score must be 100%"
    assert report.state_accuracy_avg >= 0.95, f"State accuracy {report.state_accuracy_avg:.2f} below 95%"
