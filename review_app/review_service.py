"""Core review workflow independent of Streamlit UI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from rag_app.vector_store import VectorStore
from shared.llm import LLMProvider
from shared.review_prompts import (
    build_qna_messages,
    build_summary_messages,
    build_validation_messages,
    format_citations,
    format_evidence_for_prompt,
)
from shared.retrieval import (
    build_retrieval_query,
    deduplicate_matches,
    order_matches_for_prompt,
    plan_retrieval,
    rerank_matches,
    summarize_coverage,
    trim_matches_by_budget_with_count,
)


@dataclass
class ReviewResult:
    query: str
    evidence: List[Dict[str, Any]]
    evidence_count: int
    coverage: Dict[str, Any]
    retrieval_plan: Any
    citations: List[str]
    parsed_file: Optional[Dict[str, Any]]
    answer: str

    def to_session_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "evidence": self.evidence,
            "evidence_count": self.evidence_count,
            "coverage": self.coverage,
            "retrieval_plan": self.retrieval_plan,
            "citations": self.citations,
            "parsed_file": self.parsed_file,
            "answer": self.answer,
        }


async def run_review(
    query: str,
    domain_id: str,
    parsed_file: Optional[Dict[str, Any]],
    llm: LLMProvider,
    vector_store: VectorStore,
) -> ReviewResult:
    """Run retrieval, prompt construction, and answer generation."""
    retrieval_plan = plan_retrieval(query, has_input_file=bool(parsed_file))
    retrieval_query = build_retrieval_query(
        query,
        retrieval_plan.mode,
        has_input_file=bool(parsed_file),
    )

    if retrieval_plan.use_full_domain:
        raw_matches = vector_store.list_rules(
            domain_id,
            active_only=True,
            limit=retrieval_plan.top_k,
        )
    else:
        raw_matches = vector_store.search(
            retrieval_query,
            domain_id,
            top_k=retrieval_plan.top_k,
            active_only=True,
            score_threshold=retrieval_plan.score_threshold,
        )

    matches = deduplicate_matches(raw_matches)
    deduped_count = len(matches)
    matches = rerank_matches(matches, retrieval_query, retrieval_plan.mode)
    matches = order_matches_for_prompt(matches, retrieval_plan.mode)
    matches, budget_trimmed_count = trim_matches_by_budget_with_count(matches)
    coverage = summarize_coverage(
        len(raw_matches),
        deduped_count,
        matches,
        retrieval_plan,
        budget_trimmed_count=budget_trimmed_count,
    )

    if not matches:
        raise ValueError("No evidence matched this query. Try a broader query or ingest rules first.")

    evidence_text = format_evidence_for_prompt(matches)
    citations = format_citations(matches)

    if retrieval_plan.mode == "summary":
        system, user = build_summary_messages(evidence_text, query)
    elif parsed_file:
        system, user = build_validation_messages(
            evidence_text,
            parsed_file["content"],
            query,
        )
    else:
        system, user = build_qna_messages(evidence_text, query)

    messages = llm.format_messages(system, user)
    response = await llm.complete(messages, temperature=0.1)

    return ReviewResult(
        query=query,
        evidence=matches,
        evidence_count=len(matches),
        coverage=coverage,
        retrieval_plan=retrieval_plan,
        citations=citations,
        parsed_file=parsed_file,
        answer=response.content,
    )
