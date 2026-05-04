"""Deterministic confidence scoring for review outputs."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from review_app.schema import ReviewStructuredOutput


def compute_confidence(
    coverage: Dict[str, Any],
    structured_output: Optional[ReviewStructuredOutput],
    evidence: List[Dict[str, Any]],
    invalid_citations: Optional[List[str]] = None,
    answer_text: str = "",
    query: str = "",  # Add query parameter
) -> Dict[str, Any]:
    """Compute a transparent confidence score from evidence and grounding signals."""
    score = 100
    reasons: List[str] = []
    
    # Check if this is a simple rule listing query
    rule_listing_indicators = [
        "what business rules are contained",
        "what business rules are there",
        "list all business rules",
        "what rules are in this domain",
        "show all business rules",
        "business rules in this domain",
        "contained in this domain",
        "all business rule",
        "what business rules",
    ]
    query_lower = (query or "").lower()
    answer_lower = (answer_text or "").lower()
    is_rule_listing = any(indicator in query_lower for indicator in rule_listing_indicators) or \
                      any(indicator in answer_lower for indicator in rule_listing_indicators)
    
    # For simple rule listing, don't penalize for lack of structured output
    if not is_rule_listing:
        if structured_output is None:
            score -= 30
            reasons.append("model response did not validate against the structured schema")

    if coverage.get("low_confidence"):
        score -= 20
        reasons.append("retrieval score is low")
    if coverage.get("budget_trimmed_count", 0) > 0:
        score -= 10
        reasons.append("some evidence was trimmed from the prompt budget")
    if not evidence:
        score -= 50
        reasons.append("no evidence was retrieved")
    if invalid_citations:
        score -= min(len(invalid_citations) * 10, 40)
        reasons.append(f"{len(invalid_citations)} invalid citation(s)")

    if structured_output is None and not is_rule_listing:
        score -= 30
        reasons.append("model response did not validate against the structured schema")
    elif structured_output is not None and not is_rule_listing:
        gap_count = 0
        derived_count = 0
        uncited_count = 0
        for case in structured_output.cases:
            if case.evidence_strength == "evidence_gap":
                gap_count += 1
            elif case.evidence_strength == "derived_from_rule":
                derived_count += 1
            if not case.citations:
                uncited_count += 1
        for finding in structured_output.findings:
            if finding.evidence_strength == "evidence_gap":
                gap_count += 1
            elif finding.evidence_strength == "derived_from_rule":
                derived_count += 1
            if not finding.citations:
                uncited_count += 1

        if gap_count:
            score -= min(gap_count * 8, 32)
            reasons.append(f"{gap_count} evidence-gap finding(s)")
        if derived_count:
            score -= min(derived_count * 4, 20)
            reasons.append(f"{derived_count} derived finding(s)")
        if uncited_count:
            score -= min(uncited_count * 5, 25)
            reasons.append(f"{uncited_count} uncited finding(s)")

    uncertainty_phrases = [
        "cannot be determined",
        "cannot determine",
        "can't be determined",
        "can't determine",
        "lack of specific business rules",
        "insufficient evidence",
        "not enough evidence",
        "unable to determine",
        "not possible to determine",
        "cannot identify which file",
    ]
    answer_lower = (answer_text or "").lower()
    if any(phrase in answer_lower for phrase in uncertainty_phrases):
        score = min(score, 54)
        reasons.append("answer states that evidence is insufficient or correctness cannot be determined")

    score = max(0, min(score, 100))
    if score >= 80:
        band = "high"
    elif score >= 55:
        band = "medium"
    else:
        band = "low"

    return {
        "score": score,
        "band": band,
        "reasons": reasons or ["evidence coverage and structured grounding look acceptable"],
    }
