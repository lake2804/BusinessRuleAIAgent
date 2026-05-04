from shared.rule_conflicts import detect_rule_conflicts


def test_detect_rule_conflicts_same_section_different_content():
    conflicts = detect_rule_conflicts(
        [{"section_path": "Approval", "content": "High value requires Finance approval."}],
        [
            {
                "content": "Low value requires frontline approval.",
                "metadata": {"section_path": "Approval", "source_file": "old.md", "version": "1"},
            }
        ],
        similarity_threshold=0.95,
    )

    assert conflicts
    assert conflicts[0]["existing_source"] == "old.md"
