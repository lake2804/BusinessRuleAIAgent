from shared.export_artifacts import build_corrected_file_exports, build_corrected_records
from shared.review_schema import parse_structured_review, validate_structured_citations


def test_parse_structured_review_json():
    output, error = parse_structured_review(
        """{
          "batch_summary": {},
          "cases": [{
            "case_id": "A",
            "final_decision_allowed": "conditional",
            "evidence_strength": "direct_rule"
          }],
          "human_summary": "ok"
        }"""
    )

    assert error is None
    assert output.cases[0].case_id == "A"


def test_corrected_file_exports_from_structured_output():
    output, _error = parse_structured_review(
        """{
          "corrected_records": [{"case_id": "A", "status": "hold"}],
          "cases": []
        }"""
    )
    exports = build_corrected_file_exports({"file_name": "cases.csv"}, output)

    assert "csv" in exports
    assert "txt" in exports
    assert "case_id" in exports["csv"]["content"]
    assert "xlsx" in exports
    assert "docx" in exports
    assert "pdf" in exports
    assert exports["xlsx"]["encoding"] in {"base64", "text"}


def test_corrected_records_merge_with_original_rows():
    output, _error = parse_structured_review(
        """{
          "cases": [{
            "case_id": "A",
            "final_decision_allowed": "no",
            "evidence_strength": "direct_rule",
            "required_owner_or_approver": "Risk Ops",
            "proposed_corrected_resolution": "Hold"
          }]
        }"""
    )

    records = build_corrected_records(
        {"metadata": {"records": [{"case_id": "A", "amount": "10"}]}},
        output,
    )

    assert records[0]["amount"] == "10"
    assert records[0]["business_rule_required_owner"] == "Risk Ops"


def test_validate_structured_citations_flags_unknown_ids():
    output, _error = parse_structured_review(
        """{
          "cases": [{
            "case_id": "A",
            "final_decision_allowed": "no",
            "evidence_strength": "direct_rule",
            "citations": ["S9"]
          }]
        }"""
    )

    assert validate_structured_citations(output, ["S1"]) == ["case A: S9"]
