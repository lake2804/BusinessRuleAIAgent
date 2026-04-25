"""Optional LangGraph workflow wrapper for review execution."""
from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict

from rag_app.vector_store import VectorStore
from shared.llm import LLMProvider
from review_app.review_service import ReviewResult, run_review


class ReviewState(TypedDict, total=False):
    query: str
    domain_id: str
    parsed_file: Optional[Dict[str, Any]]
    llm: LLMProvider
    vector_store: VectorStore
    result: ReviewResult


async def run_review_workflow(
    query: str,
    domain_id: str,
    parsed_file: Optional[Dict[str, Any]],
    llm: LLMProvider,
    vector_store: VectorStore,
) -> ReviewResult:
    """Run via LangGraph when available, otherwise use the service directly."""
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return await run_review(query, domain_id, parsed_file, llm, vector_store)

    async def review_node(state: ReviewState) -> ReviewState:
        result = await run_review(
            query=state["query"],
            domain_id=state["domain_id"],
            parsed_file=state.get("parsed_file"),
            llm=state["llm"],
            vector_store=state["vector_store"],
        )
        return {**state, "result": result}

    graph = StateGraph(ReviewState)
    graph.add_node("review", review_node)
    graph.set_entry_point("review")
    graph.add_edge("review", END)
    app = graph.compile()

    final_state = await app.ainvoke(
        {
            "query": query,
            "domain_id": domain_id,
            "parsed_file": parsed_file,
            "llm": llm,
            "vector_store": vector_store,
        }
    )
    return final_state["result"]
