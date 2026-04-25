import asyncio

from review_app.review_service import run_review
from shared.llm import LLMResponse


class FakeVectorStore:
    def search(self, *_args, **_kwargs):
        return [
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
            }
        ]

    def list_rules(self, *_args, **_kwargs):
        return self.search()


class FakeLLM:
    def format_messages(self, system, user):
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    async def complete(self, _messages, **_kwargs):
        return LLMResponse(content="validated", model="fake")


def test_run_review_returns_result():
    result = asyncio.run(
        run_review(
            query="Validate this case",
            domain_id="orr",
            parsed_file={"file_name": "cases.csv", "content": "case_id: IN-003"},
            llm=FakeLLM(),
            vector_store=FakeVectorStore(),
        )
    )

    assert result.answer == "validated"
    assert result.evidence_count == 1
    assert result.coverage["mode"] == "validation"
