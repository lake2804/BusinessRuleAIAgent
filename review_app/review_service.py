"""Core review workflow for strict business-rule validation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Dict, List, Optional
import uuid

from rag_app.vector_store import VectorStore
from shared.llm import LLMProvider
from shared.storage import save_review_run

from review_app.confidence import compute_confidence
from review_app.exports import build_corrected_file_exports
from review_app.schema import (
    ReviewStructuredOutput,
    normalize_citation_id,
    parse_structured_review,
    validate_structured_citations,
)
from review_app.prompts import (
    build_json_repair_messages,
    build_qna_messages,
    build_summary_messages,
    build_validation_messages,
    format_citations,
    format_evidence_for_prompt,
)
from review_app.retrieval import (
    build_retrieval_query,
    build_input_content_query,
    deduplicate_matches,
    expand_parent_child_context,
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
    structured_output: Optional[ReviewStructuredOutput] = None
    structured_error: Optional[str] = None
    confidence: Dict[str, Any] = None
    export_files: Dict[str, Dict[str, str]] = None
    case_evidence: Dict[str, List[Dict[str, Any]]] = None
    invalid_citations: List[str] = None

    def to_session_dict(self) -> Dict[str, Any]:
        retrieval_plan = (
            asdict(self.retrieval_plan)
            if is_dataclass(self.retrieval_plan)
            else self.retrieval_plan
        )
        return {
            "query": self.query,
            "evidence": self.evidence,
            "evidence_count": self.evidence_count,
            "coverage": self.coverage,
            "retrieval_plan": retrieval_plan,
            "citations": self.citations,
            "parsed_file": self.parsed_file,
            "answer": self.answer,
            "structured_output": (
                self.structured_output.model_dump() if self.structured_output else None
            ),
            "structured_error": self.structured_error,
            "confidence": self.confidence or {},
            "export_files": self.export_files or {},
            "case_evidence": self.case_evidence or {},
            "invalid_citations": self.invalid_citations or [],
        }


async def run_review(
    query: str,
    domain_id: str,
    parsed_file: Optional[Dict[str, Any]],
    llm: LLMProvider,
    vector_store: VectorStore,
    domain_name: str = "",
) -> ReviewResult:
    """Run retrieval, prompt construction, and answer generation."""
    # Inject domain context into query for better domain reference understanding
    enriched_query = _enrich_query_with_domain_context(query, domain_id, domain_name)
    retrieval_plan = plan_retrieval(enriched_query, has_input_file=bool(parsed_file), domain_id=domain_id)
    if not parsed_file and _references_unspecified_file(query):
        answer = (
            "Insufficient evidence: I cannot identify which file you want validated. "
            "Attach the file in the Review chat, then I can compare that uploaded file "
            "against the selected business-rule domain."
        )
        confidence = compute_confidence(
            {"mode": retrieval_plan.mode, "low_confidence": True},
            structured_output=None,
            evidence=[],
            answer_text=answer,
            query=query,  # Add query parameter
        )
        return ReviewResult(
            query=query,
            evidence=[],
            evidence_count=0,
            coverage={
                "mode": retrieval_plan.mode,
                "reason": "The query references an unspecified file without an attached review input.",
                "requested_top_k": retrieval_plan.top_k,
                "raw_evidence_count": 0,
                "deduped_evidence_count": 0,
                "final_evidence_count": 0,
                "unique_evidence_count": 0,
                "duplicates_removed": 0,
                "budget_trimmed_count": 0,
                "document_count": 0,
                "section_count": 0,
                "versions": [],
                "best_score": 0,
                "average_score": 0,
                "low_confidence": True,
            },
            retrieval_plan=retrieval_plan,
            citations=[],
            parsed_file=None,
            answer=answer,
            confidence=confidence,
        )

    retrieval_query = build_retrieval_query(
        enriched_query,
        retrieval_plan.mode,
        has_input_file=bool(parsed_file),
    )
    input_content_query = build_input_content_query(parsed_file)
    if input_content_query:
        retrieval_query = f"{retrieval_query}\n\nUploaded input content for retrieval:\n{input_content_query}"

    case_queries = _build_case_queries(parsed_file)
    case_evidence: Dict[str, List[Dict[str, Any]]] = {}

    if case_queries and not retrieval_plan.use_full_domain:
        raw_matches = []
        case_top_k = _adaptive_case_top_k(retrieval_plan.top_k, len(case_queries))
        for case_id, case_query in case_queries:
            case_retrieval_query = build_retrieval_query(
                f"{enriched_query}\nCase {case_id}:\n{case_query}",
                retrieval_plan.mode,
                has_input_file=True,
            )
            try:
                case_matches = vector_store.search(
                    case_retrieval_query,
                    domain_id,
                    top_k=case_top_k,
                    active_only=True,
                    score_threshold=retrieval_plan.score_threshold,
                )
            except Exception as e:
                raise ValueError(f"Vector store search error for case '{case_id}' in domain '{domain_id}': {str(e)}")
            case_evidence[case_id] = case_matches
            raw_matches.extend(case_matches)
    elif retrieval_plan.use_full_domain:
        try:
            raw_matches = vector_store.list_rules(
                domain_id,
                active_only=True,
                limit=retrieval_plan.top_k,
            )
        except Exception as e:
            raise ValueError(f"Vector store error listing rules for domain '{domain_id}': {str(e)}")
    else:
        try:
            raw_matches = vector_store.search(
                retrieval_query,
                domain_id,
                top_k=retrieval_plan.top_k,
                active_only=True,
                score_threshold=retrieval_plan.score_threshold,
            )
        except Exception as e:
            raise ValueError(f"Vector store search error for domain '{domain_id}': {str(e)}")

    raw_matches = _include_domain_match_evidence(raw_matches, parsed_file, vector_store, domain_id)
    target_document_ids = _target_document_ids(parsed_file)
    raw_matches = _exclude_target_document_evidence(raw_matches, target_document_ids)
    matches = deduplicate_matches(raw_matches)
    deduped_count = len(matches)
    matches = rerank_matches(matches, retrieval_query, retrieval_plan.mode)
    if matches:
        try:
            context_pool = vector_store.list_rules(
                domain_id,
                active_only=True,
                limit=min(max(len(matches) * 4, 50), 300),
            )
        except Exception as e:
            raise ValueError(f"Vector store error fetching context pool for domain '{domain_id}': {str(e)}")
        matches = expand_parent_child_context(matches, context_pool)
        matches = _exclude_target_document_evidence(matches, target_document_ids)
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
        raise ValueError(f"No evidence matched this query in domain '{domain_id}'. Try a broader query or ingest rules first.")

    evidence_text = format_evidence_for_prompt(matches)
    citations = format_citations(matches)

    if retrieval_plan.mode == "summary":
        system, user = build_summary_messages(evidence_text, enriched_query, domain_id, domain_name)
    elif parsed_file:
        input_content = _format_parsed_input_for_prompt(parsed_file)
        system, user = build_validation_messages(
            evidence_text,
            input_content,
            enriched_query,
            domain_id,
            domain_name,
        )
    else:
        system, user = build_qna_messages(evidence_text, enriched_query, domain_id, domain_name)

    messages = llm.format_messages(system, user)
    response = await llm.complete(messages, temperature=0.1)
    structured_output, structured_error = (
        parse_structured_review(response.content) if parsed_file else (None, None)
    )
    if parsed_file and structured_output is None and structured_error:
        repair_system, repair_user = build_json_repair_messages(response.content, structured_error)
        repair_response = await llm.complete(
            llm.format_messages(repair_system, repair_user),
            temperature=0.0,
        )
        repaired_output, repair_error = parse_structured_review(repair_response.content)
        if repaired_output is not None:
            structured_output = repaired_output
            structured_error = None
            response = repair_response
        else:
            structured_error = f"{structured_error}; repair failed: {repair_error}"

    valid_citations = [normalize_citation_id(citation.split("]", 1)[0] + "]") for citation in citations]
    invalid_citations = (
        validate_structured_citations(structured_output, valid_citations)
        if structured_output
        else []
    )
    confidence = compute_confidence(
        coverage,
        structured_output,
        evidence=matches,
        answer_text=response.content,
        query=query,
    )
    export_files = build_corrected_file_exports(parsed_file, structured_output)

    result = ReviewResult(
        query=query,
        evidence=matches,
        evidence_count=len(matches),
        coverage=coverage,
        retrieval_plan=retrieval_plan,
        citations=citations,
        parsed_file=parsed_file,
        answer=response.content,
        structured_output=structured_output,
        structured_error=structured_error,
        confidence=confidence,
        export_files=export_files,
        case_evidence=case_evidence,
        invalid_citations=invalid_citations,
    )
    try:
        save_review_run(
            review_id=str(uuid.uuid4()),
            domain_id=domain_id,
            query=query,
            input_file=parsed_file.get("file_name", "") if parsed_file else "",
            confidence=result.confidence,
            structured_output=result.to_session_dict().get("structured_output"),
            evidence=result.evidence,
            exports=result.export_files,
        )
    except Exception:
        pass
    return result


def _build_case_queries(parsed_file: Optional[Dict[str, Any]]) -> List[tuple[str, str]]:
    if not parsed_file:
        return []
    records = parsed_file.get("metadata", {}).get("records") or []
    if not isinstance(records, list) or not records:
        return []

    case_queries = []
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            continue
        case_id = str(
            record.get("case_id")
            or record.get("id")
            or record.get("case")
            or f"row_{index}"
        )
        compact = "\n".join(
            f"{key}: {value}" for key, value in record.items() if value not in (None, "")
        )
        if compact:
            case_queries.append((case_id, compact))
    return case_queries


def _adaptive_case_top_k(base_top_k: int, case_count: int) -> int:
    if case_count <= 10:
        return base_top_k
    if case_count <= 50:
        return max(8, base_top_k // 2)
    return max(4, base_top_k // 4)


def _references_unspecified_file(query: str) -> bool:
    query_lower = query.lower()
    file_references = (
        "this file",
        "the file",
        "uploaded file",
        "attached file",
        "following file",
    )
    validation_words = ("correct", "valid", "validate", "check", "comply", "compliance")
    return any(term in query_lower for term in file_references) and any(
        term in query_lower for term in validation_words
    )


def _format_parsed_input_for_prompt(parsed_file: Dict[str, Any]) -> str:
    file_name = parsed_file.get("file_name") or "uploaded_file"
    file_type = parsed_file.get("file_type") or parsed_file.get("metadata", {}).get("file_type") or "unknown"
    content = parsed_file.get("content", "")
    domain_match_text = _format_domain_matches(parsed_file)
    return f"Uploaded file name: {file_name}\nUploaded file type: {file_type}\n{domain_match_text}\n\n{content}"


def _target_document_ids(parsed_file: Optional[Dict[str, Any]]) -> set[str]:
    if not parsed_file:
        return set()
    document_ids = parsed_file.get("metadata", {}).get("document_ids") or []
    return {str(item) for item in document_ids if item}


def _exclude_target_document_evidence(
    matches: List[Dict[str, Any]],
    target_document_ids: set[str],
) -> List[Dict[str, Any]]:
    if not target_document_ids:
        return matches
    return [
        match for match in matches
        if str(match.get("metadata", {}).get("document_id", "")) not in target_document_ids
    ]


def _domain_matches(parsed_file: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not parsed_file:
        return []
    metadata = parsed_file.get("metadata", {})
    matches = metadata.get("domain_matches") or []
    return matches if isinstance(matches, list) else []


def _include_domain_match_evidence(
    matches: List[Dict[str, Any]],
    parsed_file: Optional[Dict[str, Any]],
    vector_store: VectorStore,
    domain_id: str,
) -> List[Dict[str, Any]]:
    document_ids = {
        str(item.get("document_id"))
        for item in _domain_matches(parsed_file)
        if item.get("document_id")
    }
    if not document_ids:
        return matches

    existing_chunk_ids = {item.get("chunk_id") for item in matches}
    additions = []
    try:
        all_rules = vector_store.list_rules(domain_id, active_only=True)
    except Exception as e:
        raise ValueError(f"Vector store error listing rules for domain match evidence: {str(e)}")
    
    for item in all_rules:
        metadata = item.get("metadata", {})
        if str(metadata.get("document_id", "")) not in document_ids:
            continue
        if item.get("chunk_id") in existing_chunk_ids:
            continue
        enriched = dict(item)
        enriched["domain_match_evidence"] = True
        enriched["score"] = max(float(enriched.get("score", 0)), 0.98)
        additions.append(enriched)
    return additions + matches


def _enrich_query_with_domain_context(query: str, domain_id: str, domain_name: str) -> str:
    """Enrich query with domain context to help AI understand domain references.
    
    When user mentions domain name/ID in query, this helps AI map it to the selected domain.
    """
    if not domain_id:
        return query
    
    # If query already mentions the domain name or ID, add explicit context
    query_lower = query.lower()
    domain_hints = [domain_id.lower()]
    if domain_name:
        domain_hints.append(domain_name.lower())
    
    # Check if query seems to reference the domain
    mentions_domain = any(hint in query_lower for hint in domain_hints)
    
    if mentions_domain:
        # Inject explicit context about what this domain refers to
        context = f"[Current domain context: domain_id='{domain_id}'"
        if domain_name:
            context += f", domain_name='{domain_name}'"
        context += "]\n"
        return context + query
    
    return query


def _format_domain_matches(parsed_file: Dict[str, Any]) -> str:
    matches = _domain_matches(parsed_file)
    if not matches:
        return "\nDomain knowledge match: no exact or filename match found in the selected domain."
    lines = ["\nDomain knowledge matches for uploaded file(s):"]
    for item in matches:
        lines.append(
            "- "
            f"{item.get('source_file', 'unknown')} "
            f"({item.get('match_type', 'unknown_match')}, "
            f"document_id={item.get('document_id', 'unknown')}, "
            f"version={item.get('version', 'unknown')}, "
            f"status={item.get('status', 'unknown')})"
        )
    return "\n".join(lines)
