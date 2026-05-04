"""Run lightweight validation benchmarks against the review workflow.

This runner uses deterministic fake evidence/LLM responses by default so it can
run in CI without API keys. It verifies benchmark fixture shape and structured
output expectations. Wire a real vector store/LLM later for live regression.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from review_app.review_service import run_review
from shared.llm import LLMResponse


class EvalVectorStore:
    def search(self, *_args, **_kwargs):
        return [
            {
                "chunk_id": "eval-1",
                "content": (
                    "Fraud hold requires Risk Ops review. Changed payment "
                    "destination requires Finance review and payment hold. "
                    "Region is a mandatory input."
                ),
                "metadata": {
                    "source_file": "eval_rules.md",
                    "section_path": "Evaluation Rules",
                    "version": "eval",
                    "status": "active",
                    "active": True,
                },
                "score": 0.9,
            }
        ]

    def list_rules(self, *_args, **_kwargs):
        return self.search()


class EvalLLM:
    def __init__(self, case: Dict[str, Any]):
        self.case = case

    def format_messages(self, system, user):
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    async def complete(self, _messages, **_kwargs):
        input_record = self.case["input"]
        case_id = input_record.get("case_id", self.case["id"])
        issue_types = self.case.get("expected_issue_types", [])
        owner = ", ".join(self.case.get("expected_owner_terms", []))
        return LLMResponse(
            model="eval",
            content=json.dumps(
                {
                    "batch_summary": {"case_count": 1},
                    "cases": [
                        {
                            "case_id": case_id,
                            "directly_evidenced_findings": issue_types,
                            "issue_types": issue_types,
                            "final_decision_allowed": "no",
                            "proposed_corrected_resolution": "Correct according to cited rules.",
                            "required_owner_or_approver": owner,
                            "evidence_strength": "direct_rule",
                            "citations": ["S1"],
                            "corrected_record": {
                                **input_record,
                                "business_rule_status": "needs_review",
                            },
                        }
                    ],
                    "cited_sources": ["S1"],
                    "human_summary": "Evaluation response.",
                }
            ),
        )


async def run_case(case: Dict[str, Any]) -> Dict[str, Any]:
    parsed_file = {
        "file_name": f"{case['id']}.json",
        "content": json.dumps(case["input"]),
        "metadata": {"records": [case["input"]]},
    }
    result = await run_review(
        query=case["query"],
        domain_id="eval",
        parsed_file=parsed_file,
        llm=EvalLLM(case),
        vector_store=EvalVectorStore(),
    )
    structured = result.structured_output
    actual_issues = set(structured.cases[0].issue_types if structured and structured.cases else [])
    expected_issues = set(case.get("expected_issue_types", []))
    owner_text = structured.cases[0].required_owner_or_approver if structured and structured.cases else ""
    owner_ok = all(term in owner_text for term in case.get("expected_owner_terms", []))
    return {
        "id": case["id"],
        "passed": expected_issues.issubset(actual_issues) and owner_ok and not result.invalid_citations,
        "expected_issue_types": sorted(expected_issues),
        "actual_issue_types": sorted(actual_issues),
        "confidence": result.confidence,
        "invalid_citations": result.invalid_citations,
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="eval_cases/orr_validation_benchmark.json")
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    results = [await run_case(case) for case in cases]
    print(json.dumps({"passed": all(item["passed"] for item in results), "results": results}, indent=2))
    raise SystemExit(0 if all(item["passed"] for item in results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
