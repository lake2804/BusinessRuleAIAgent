from rag_app.parsers.business_rule_parser import BusinessRuleFileParser


def test_business_rule_parser_supports_json(tmp_path):
    file_path = tmp_path / "rules.json"
    file_path.write_text('{"region": "SG", "rule": "visual evidence required"}', encoding="utf-8")

    text, chunks = BusinessRuleFileParser().parse(file_path)

    assert "visual evidence required" in text
    assert chunks


def test_business_rule_parser_preserves_markdown_table_section(tmp_path):
    file_path = tmp_path / "rules.md"
    file_path.write_text(
        "# Escalation Matrix\n\nScenario | Owner | Action\n--- | --- | ---\nFraud hold | Risk Ops | Review",
        encoding="utf-8",
    )

    _text, chunks = BusinessRuleFileParser().parse(file_path)

    assert any("Table" in chunk["section_path"] for chunk in chunks)
    assert any("Fraud hold" in chunk["content"] for chunk in chunks)
