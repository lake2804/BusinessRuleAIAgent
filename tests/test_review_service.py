import asyncio

from review_app.review_service import run_review
from shared.llm import LLMResponse


class FakeVectorStore:
    def search(self, *_args, **_kwargs):
        return [
            {
                "chunk_id": "fixture",
                "content": "README test fixture should not dominate.",
                "metadata": {
                    "source_file": "README_Test_Pack.md",
                    "section_path": "Test Notes",
                    "version": "1.0.0",
                    "status": "active",
                    "active": True,
                },
                "score": 0.95,
            },
            {
                "chunk_id": "1",
                "content": "Fraud hold requires Risk Ops review.",
                "metadata": {
                    "source_file": "rules.md",
                    "section_path": "Fraud",
                    "version": "1.0.0",
                    "status": "active",
                    "active": True,
                },
                "score": 0.7,
            },
            {
                "chunk_id": "target",
                "content": "Target document content should not validate itself.",
                "metadata": {
                    "document_id": "target-doc",
                    "source_file": "target.pdf",
                    "section_path": "Self",
                    "version": "1.0.0",
                    "status": "active",
                    "active": True,
                },
                "score": 0.99,
            }
        ]

    def list_rules(self, *_args, **_kwargs):
        return self.search()


class FakeLLM:
    def format_messages(self, system, user):
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    async def complete(self, _messages, **_kwargs):
        return LLMResponse(
            content="""{
              "batch_summary": {"final_decision_allowed": {"no": 1}},
              "cases": [{
                "case_id": "IN-003",
                "directly_evidenced_findings": ["Fraud hold requires Risk Ops review."],
                "issue_types": ["hard_restriction"],
                "final_decision_allowed": "no",
                "proposed_corrected_resolution": "Hold for Risk Ops review.",
                "required_owner_or_approver": "Risk Ops",
                "evidence_strength": "direct_rule",
                "inference_or_needs_confirmation": "",
                "citations": ["S1"],
                "corrected_record": {"case_id": "IN-003", "status": "hold"}
              }],
              "findings": [],
              "grounding_warnings": [],
              "cited_sources": ["S1"],
              "corrected_records": [{"case_id": "IN-003", "status": "hold"}],
              "human_summary": "validated"
            }""",
            model="fake",
        )


def test_run_review_returns_result():
    result = asyncio.run(
        run_review(
            query="Validate this case",
            domain_id="orr",
            parsed_file={
                "file_name": "cases.csv",
                "content": "case_id: IN-003",
                "metadata": {
                    "domain_matches": [
                        {
                            "match_type": "exact_content_hash",
                            "document_id": "matched-doc",
                            "source_file": "cases.csv",
                            "version": "1.0.0",
                            "status": "active",
                        }
                    ],
                    "document_ids": ["target-doc"],
                    "records": [{"case_id": "IN-003", "status": "pending"}],
                },
            },
            llm=FakeLLM(),
            vector_store=FakeVectorStore(),
        )
    )

    assert result.structured_output.human_summary == "validated"
    assert result.evidence_count == 1
    assert result.coverage["mode"] == "validation"
    assert result.confidence["band"] in {"medium", "high"}
    assert "csv" in result.export_files
    assert all("README_Test_Pack" not in item["metadata"].get("source_file", "") for item in result.evidence)
    assert all(item["metadata"].get("document_id") != "target-doc" for item in result.evidence)


def test_run_review_includes_domain_match_evidence():
    class MatchingVectorStore(FakeVectorStore):
        def search(self, *_args, **_kwargs):
            return []

        def list_rules(self, *_args, **_kwargs):
            return [
                {
                    "chunk_id": "matched",
                    "content": "Matched domain document rule content.",
                    "metadata": {
                        "document_id": "matched-doc",
                        "source_file": "cases.csv",
                        "section_path": "Matched",
                        "version": "1.0.0",
                        "status": "active",
                        "active": True,
                    },
                    "score": 1.0,
                }
            ]

    result = asyncio.run(
        run_review(
            query="Is this file correct due to the business rule?",
            domain_id="orr",
            parsed_file={
                "file_name": "cases.csv",
                "content": "case_id: IN-003",
                "metadata": {
                    "domain_matches": [
                        {
                            "match_type": "exact_content_hash",
                            "document_id": "matched-doc",
                            "source_file": "cases.csv",
                        }
                    ]
                },
            },
            llm=FakeLLM(),
            vector_store=MatchingVectorStore(),
        )
    )

    assert result.evidence_count == 1
    assert result.evidence[0]["metadata"]["document_id"] == "matched-doc"


def test_run_review_handles_unspecified_file_reference_without_high_confidence():
    result = asyncio.run(
        run_review(
            query="Is this file correct due to the business rule?",
            domain_id="orr",
            parsed_file=None,
            llm=FakeLLM(),
            vector_store=FakeVectorStore(),
        )
    )

    assert "cannot identify which file" in result.answer
    assert result.evidence_count == 0
    assert result.confidence["band"] == "low"


def test_run_review_builds_case_queries_for_all_rows():
    records = [{"case_id": f"IN-{index:03d}", "status": "pending"} for index in range(250)]
    result = asyncio.run(
        run_review(
            query="Validate every row",
            domain_id="orr",
            parsed_file={
                "file_name": "large.csv",
                "content": "large batch",
                "metadata": {"records": records},
            },
            llm=FakeLLM(),
            vector_store=FakeVectorStore(),
        )
    )

    assert len(result.case_evidence) == 250
