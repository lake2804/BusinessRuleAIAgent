from shared.review_prompts import (
    ISSUE_TAXONOMY,
    build_validation_messages,
    format_citations,
    format_evidence_for_prompt,
)


def test_validation_prompt_contains_grounding_requirements():
    system, user = build_validation_messages("Evidence [S1]", "case_id: IN-001", "Validate")

    assert "evidence_strength" in system
    assert "invalid_or_unsupported_input" in ISSUE_TAXONOMY
    assert "Do not state numeric approval thresholds" in system
    assert "case_id: IN-001" in user


def test_citation_labels_match_evidence_labels_with_duplicate_sections():
    matches = [
        {
            "content": "first rule",
            "metadata": {"source_file": "rules.pdf", "section_path": "A", "version": "1", "source_page": 0},
            "score": 0.9,
        },
        {
            "content": "second rule",
            "metadata": {"source_file": "rules.pdf", "section_path": "A", "version": "1", "source_page": 0},
            "score": 0.8,
        },
    ]

    evidence = format_evidence_for_prompt(matches)
    citations = format_citations(matches)

    assert "[S1]" in evidence
    assert "[S2]" in evidence
    assert citations[0].startswith("[S1]")
    assert citations[1].startswith("[S2]")
    assert "page 0" in citations[0]
