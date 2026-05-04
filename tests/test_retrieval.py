from shared.retrieval import (
    build_input_content_query,
    deduplicate_matches,
    detect_query_mode,
    filter_low_value_evidence,
    plan_retrieval,
    rerank_matches,
    summarize_coverage,
    trim_matches_by_budget_with_count,
    expand_parent_child_context,
)


def test_detect_query_mode_validation_when_file_present():
    assert detect_query_mode("Please review this batch", has_input_file=True) == "validation"
    assert detect_query_mode("Is this file correct due to the business rule?") == "validation"


def test_detect_query_mode_uses_whole_words():
    assert detect_query_mode("Explain the checkout flow") == "qna"
    assert detect_query_mode("Compare regional override rules") == "analysis"


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


def test_deduplicate_matches_keeps_unidentified_distinct_chunks():
    matches = [
        {"chunk_id": "a", "content": "same rule", "metadata": {}, "score": 0.4},
        {"chunk_id": "b", "content": "same rule", "metadata": {}, "score": 0.5},
    ]
    assert len(deduplicate_matches(matches)) == 2


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


def test_trim_matches_truncates_first_oversized_match():
    matches = [
        {"content": "a" * 20, "metadata": {}, "score": 1.0},
        {"content": "second", "metadata": {}, "score": 0.9},
    ]
    trimmed, dropped = trim_matches_by_budget_with_count(matches, max_chars=10)
    assert len(trimmed) == 1
    assert len(trimmed[0]["content"]) == 10
    assert trimmed[0]["metadata"]["content_truncated"] is True
    assert dropped == 1


def test_summarize_coverage_separates_dedup_and_budget_trim():
    plan = plan_retrieval("Validate cases", True)
    coverage = summarize_coverage(
        raw_count=5,
        deduped_count=3,
        matches=[{"content": "rule", "metadata": {"source_file": "a"}, "score": 0.9}],
        plan=plan,
        budget_trimmed_count=2,
    )
    assert coverage["duplicates_removed"] == 2
    assert coverage["budget_trimmed_count"] == 2


def test_expand_parent_child_context_adds_parent():
    matches = [{"chunk_id": "child", "content": "child", "metadata": {"parent_id": "parent"}, "score": 0.8}]
    pool = [
        {"chunk_id": "parent", "content": "parent", "metadata": {}, "score": 1.0},
        {"chunk_id": "child", "content": "child", "metadata": {"parent_id": "parent"}, "score": 0.8},
    ]

    expanded = expand_parent_child_context(matches, pool)

    assert any(item["chunk_id"] == "parent" for item in expanded)


def test_build_input_content_query_includes_uploaded_content():
    query = build_input_content_query(
        {"file_name": "handbook.pdf", "file_type": "pdf", "content": "Escalation matrix"}
    )
    assert "handbook.pdf" in query
    assert "Escalation matrix" in query


def test_filter_low_value_evidence_removes_test_fixtures_for_validation():
    matches = [
        {"content": "fixture", "metadata": {"source_file": "README_Test_Pack.md"}, "score": 0.9},
        {"content": "policy", "metadata": {"source_file": "ORR_Policy_Manual.docx"}, "score": 0.8},
    ]
    filtered = filter_low_value_evidence(matches, "validation")
    assert len(filtered) == 1
    assert filtered[0]["content"] == "policy"
