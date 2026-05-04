from shared.confidence import compute_confidence
from shared.retrieval import plan_retrieval, summarize_coverage


def test_confidence_caps_uncertain_answers():
    plan = plan_retrieval("Validate this file", has_input_file=True)
    evidence = [{"content": "rule", "metadata": {"source_file": "policy"}, "score": 0.9}]
    coverage = summarize_coverage(1, 1, evidence, plan)

    confidence = compute_confidence(
        coverage,
        structured_output=None,
        evidence=evidence,
        answer_text="Correctness cannot be determined due to insufficient evidence.",
    )

    assert confidence["score"] <= 54
    assert confidence["band"] != "high"
