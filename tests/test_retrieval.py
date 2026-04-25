from shared.retrieval import (
    deduplicate_matches,
    detect_query_mode,
    plan_retrieval,
    rerank_matches,
)


def test_detect_query_mode_validation_when_file_present():
    assert detect_query_mode("Please review this batch", has_input_file=True) == "validation"


def test_plan_retrieval_uses_wider_validation_top_k():
    plan = plan_retrieval("Validate every row against the ORR business-rule domain.", True)
    assert plan.mode == "validation"
    assert plan.top_k >= 18
    assert plan.score_threshold is not None


def test_deduplicate_matches_keeps_highest_score():
    matches = [
        {
            "content": "same rule",
            "metadata": {"document_id": "doc", "section_path": "A"},
            "score": 0.2,
        },
        {
            "content": "same rule",
            "metadata": {"document_id": "doc", "section_path": "A"},
            "score": 0.8,
        },
    ]
    deduped = deduplicate_matches(matches)
    assert len(deduped) == 1
    assert deduped[0]["score"] == 0.8


def test_rerank_boosts_exact_validation_terms():
    matches = [
        {
            "content": "general policy overview",
            "metadata": {"status": "active"},
            "score": 0.5,
        },
        {
            "content": "approval threshold and regional manager owner",
            "metadata": {"status": "active"},
            "score": 0.45,
        },
    ]
    reranked = rerank_matches(matches, "approval threshold regional manager", "validation")
    assert reranked[0]["content"].startswith("approval threshold")
