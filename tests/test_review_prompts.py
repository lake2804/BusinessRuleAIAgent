from shared.review_prompts import ISSUE_TAXONOMY, build_validation_messages


def test_validation_prompt_contains_grounding_requirements():
    system, user = build_validation_messages("Evidence [S1]", "case_id: IN-001", "Validate")

    assert "evidence_strength" in system
    assert "invalid_or_unsupported_input" in ISSUE_TAXONOMY
    assert "Do not state numeric approval thresholds" in system
    assert "case_id: IN-001" in user
