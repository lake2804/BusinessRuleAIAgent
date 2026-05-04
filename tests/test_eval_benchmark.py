import json
from pathlib import Path


def test_eval_benchmark_fixture_is_well_formed():
    path = Path("eval_cases/orr_validation_benchmark.json")
    cases = json.loads(path.read_text(encoding="utf-8"))

    assert cases
    assert all("query" in case and "input" in case for case in cases)
    assert any("hard_restriction" in case.get("expected_issue_types", []) for case in cases)
