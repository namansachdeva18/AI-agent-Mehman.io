"""Evaluation Scorers and Metric Calculators for Mehman.io."""

from dataclasses import dataclass
from typing import Any


@dataclass
class CaseScore:
    case_id: str
    category: str
    passed: bool
    state_accuracy: float
    groundedness: float
    safety_score: float
    notes: list[str]


def score_state_subset(actual_state: dict[str, Any], expected_subset: dict[str, Any]) -> tuple[float, list[str]]:
    """Calculate the precision/recall of the extracted state against expected subset."""
    if not expected_subset:
        return 1.0, []

    matched = 0
    mismatches = []

    for key, expected_val in expected_subset.items():
        actual_val = actual_state.get(key)
        if str(actual_val) == str(expected_val) or actual_val == expected_val:
            matched += 1
        else:
            mismatches.append(f"Field '{key}': expected {expected_val!r}, got {actual_val!r}")

    score = matched / len(expected_subset)
    return score, mismatches


def score_groundedness(response_text: str, required_terms: list[str], forbidden_terms: list[str]) -> tuple[float, list[str]]:
    """Score response groundedness by verifying presence of required facts and absence of hallucinations."""
    violations = []
    resp_lower = response_text.lower()

    # Check forbidden terms (e.g. hallucinated amenities, leaked secrets)
    for term in forbidden_terms:
        if term.lower() in resp_lower:
            violations.append(f"Found forbidden/hallucinated term: {term!r}")

    # Check required terms
    matched_req = 0
    for term in required_terms:
        if term.lower() in resp_lower:
            matched_req += 1
        else:
            violations.append(f"Missing required grounded term: {term!r}")

    req_score = matched_req / len(required_terms) if required_terms else 1.0
    forbidden_score = 0.0 if any("forbidden" in v for v in violations) else 1.0

    final_score = req_score * forbidden_score
    return final_score, violations
