"""Retrieval planning and evidence post-processing helpers."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


SUMMARY_TERMS = [
    "go through",
    "tell me detail",
    "tell me everything",
    "what is mentioned",
    "summarize all",
    "all business rule",
    "entire business rule",
    "full summary",
    "overview",
]

VALIDATION_TERMS = [
    "validate",
    "validation",
    "check",
    "correct",
    "comply",
    "complies",
    "complying",
    "compliance",
    "verify",
    "valid",
]
ANALYSIS_TERMS = ["analyze", "analysis", "compare", "comparison", "difference", "trend", "pattern"]


@dataclass(frozen=True)
class RetrievalPlan:
    mode: str
    top_k: int
    use_full_domain: bool
    score_threshold: float | None
    reason: str


def detect_query_mode(query: str, has_input_file: bool = False) -> str:
    query_lower = query.lower()
    tokens = set(re.findall(r"\b[\w+-]+\b", query_lower))
    if _matches_mode_terms(query_lower, tokens, SUMMARY_TERMS):
        return "summary"
    if has_input_file or _matches_mode_terms(query_lower, tokens, VALIDATION_TERMS):
        return "validation"
    if _matches_mode_terms(query_lower, tokens, ANALYSIS_TERMS):
        return "analysis"
    return "qna"


def _matches_mode_terms(query_lower: str, tokens: set[str], terms: List[str]) -> bool:
    for term in terms:
        if " " in term:
            if re.search(rf"\b{re.escape(term)}\b", query_lower):
                return True
        elif term in tokens:
            return True
    return False


def get_adaptive_top_k(domain_id: str, base_top_k: int, max_top_k: int = 50) -> int:
    """Adaptive top-k based on domain document count."""
    from shared.storage import list_documents
    from rag_app.vector_store import VectorStore
    
    # Count documents in domain
    docs = list_documents(domain_id)
    doc_count = len(docs)
    
    # Count chunks in vector store
    vector_store = VectorStore()
    try:
        vector_store.initialize()
        chunks = vector_store.list_rules(domain_id, active_only=True, limit=1000)
        chunk_count = len(chunks)
    except:
        chunk_count = 0
    
    # Adaptive logic
    if doc_count <= 3:
        # Small domain: retrieve more from each doc
        adaptive_k = min(base_top_k * 2, max_top_k)
    elif doc_count <= 6:
        # Medium domain: moderate increase
        adaptive_k = min(base_top_k * 1.5, max_top_k)
    elif doc_count <= 10:
        # Large domain: slight increase
        adaptive_k = min(base_top_k * 1.2, max_top_k)
    else:
        # Very large domain: keep base but ensure minimum
        adaptive_k = max(base_top_k, 20)
    
    # Ensure we don't exceed available chunks
    if chunk_count > 0:
        adaptive_k = min(adaptive_k, chunk_count)
    
    return int(adaptive_k)


def plan_retrieval(query: str, has_input_file: bool = False, domain_id: str = "") -> RetrievalPlan:
    mode = detect_query_mode(query, has_input_file=has_input_file)
    word_count = len(re.findall(r"\w+", query))

    if mode == "summary":
        base_top_k = 200
        adaptive_top_k = get_adaptive_top_k(domain_id, base_top_k, max_top_k=200) if domain_id else base_top_k
        return RetrievalPlan(
            mode=mode,
            top_k=adaptive_top_k,
            use_full_domain=True,
            score_threshold=None,
            reason=f"Broad summary request; reviewing all active domain evidence (adaptive top-k: {adaptive_top_k}).",
        )

    if mode == "validation":
        base_top_k = 24 if word_count > 20 else 18
        adaptive_top_k = get_adaptive_top_k(domain_id, base_top_k, max_top_k=50) if domain_id else base_top_k
        return RetrievalPlan(
            mode=mode,
            top_k=adaptive_top_k,
            use_full_domain=False,
            score_threshold=0.12,
            reason=f"Validation request; retrieving a wider evidence set (adaptive top-k: {adaptive_top_k}).",
        )

    if mode == "analysis":
        base_top_k = 16 if word_count > 16 else 12
        adaptive_top_k = get_adaptive_top_k(domain_id, base_top_k, max_top_k=40) if domain_id else base_top_k
        return RetrievalPlan(
            mode=mode,
            top_k=adaptive_top_k,
            use_full_domain=False,
            score_threshold=0.18,
            reason=f"Analysis request; retrieving enough evidence for comparison (adaptive top-k: {adaptive_top_k}).",
        )

    base_top_k = 10 if word_count > 14 else 6
    adaptive_top_k = get_adaptive_top_k(domain_id, base_top_k, max_top_k=30) if domain_id else base_top_k
    return RetrievalPlan(
        mode=mode,
        top_k=adaptive_top_k,
        use_full_domain=False,
        score_threshold=0.15,
        reason=f"Focused Q&A request; retrieving more evidence for comprehensive coverage (adaptive top-k: {adaptive_top_k}).",
    )


def build_retrieval_query(query: str, mode: str, has_input_file: bool = False) -> str:
    """Expand broad validation queries with terms that improve rule coverage."""
    if mode != "validation":
        return query

    validation_terms = [
        "policy principles",
        "business rule requirements",
        "rule consistency",
        "contradiction",
        "conflict",
        "exception",
        "effective date",
        "active policy",
        "document status",
        "mandatory input",
        "missing field",
        "valid region",
        "unsupported region",
        "GLOBAL region",
        "policy version",
        "approval owner",
        "approver",
        "approval threshold",
        "amount band",
        "tier authority",
        "finance control manager",
        "regional manager",
        "escalation",
        "hard restriction",
        "fraud hold",
        "payment redirection",
        "regional override",
        "evidence requirement",
        "buyer remorse",
        "opened seal",
        "seal intact",
        "refund condition",
        "return condition",
        "damaged item",
        "perishable",
        "visual evidence",
        "same-day",
        "SLA",
        "corrected resolution",
    ]
    file_hint = " parsed input file rules cases rows document content" if has_input_file else ""
    return f"{query}{file_hint}\n" + "\n".join(validation_terms)


def build_input_content_query(parsed_file: Dict[str, Any] | None, max_chars: int = 3500) -> str:
    """Extract a compact retrieval hint from an uploaded file."""
    if not parsed_file:
        return ""
    file_name = parsed_file.get("file_name", "")
    file_type = parsed_file.get("file_type", "")
    content = parsed_file.get("content", "")
    if not isinstance(content, str):
        content = str(content)
    return f"Uploaded file: {file_name}\nFile type: {file_type}\n{content[:max_chars]}"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _content_hash(text: str) -> str:
    return hashlib.sha256(_normalize_text(text).encode("utf-8")).hexdigest()


def deduplicate_matches(matches: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate evidence while keeping the highest-scoring copy."""
    best_by_key: Dict[tuple, Dict[str, Any]] = {}

    for match in matches:
        metadata = match.get("metadata", {})
        source_id = metadata.get("document_id") or metadata.get("source_file")
        if not source_id:
            source_id = match.get("chunk_id") or f"unidentified:{id(match)}"
        key = (
            source_id,
            metadata.get("section_path") or "",
            _content_hash(match.get("content", "")),
        )
        existing = best_by_key.get(key)
        if existing is None or match.get("score", 0) > existing.get("score", 0):
            best_by_key[key] = match

    return sorted(best_by_key.values(), key=lambda item: item.get("score", 0), reverse=True)


def _query_terms(query: str) -> set[str]:
    return {
        term.lower()
        for term in re.findall(r"[A-Za-z0-9_+-]{3,}", query)
        if term.lower() not in {"the", "and", "for", "with", "this", "that", "from"}
    }


def rerank_matches(matches: List[Dict[str, Any]], query: str, mode: str) -> List[Dict[str, Any]]:
    """Apply a transparent heuristic reranker after vector retrieval."""
    query_terms = _query_terms(query)
    validation_boost_terms = {
        "owner",
        "approver",
        "approval",
        "threshold",
        "amount",
        "region",
        "override",
        "evidence",
        "fraud",
        "hold",
        "seal",
        "refund",
        "return",
        "sla",
    }

    reranked = []
    for match in matches:
        metadata = match.get("metadata", {})
        content = _normalize_text(match.get("content", ""))
        metadata_text = _normalize_text(" ".join(str(value) for value in metadata.values()))
        haystack = f"{content} {metadata_text}"

        score = float(match.get("score", 0))
        exact_hits = sum(1 for term in query_terms if term.lower() in haystack)
        score += min(exact_hits * 0.03, 0.3)
        lexical_overlap = exact_hits / max(len(query_terms), 1)
        score += min(lexical_overlap * 0.2, 0.2)
        updated_lexical_score = lexical_overlap

        if mode == "validation":
            validation_hits = sum(1 for term in validation_boost_terms if term in haystack)
            score += min(validation_hits * 0.02, 0.2)

        if metadata.get("active") is True or str(metadata.get("status", "")).lower() == "active":
            score += 0.05
        if str(metadata.get("status", "")).lower() == "archived":
            score -= 0.15

        updated = dict(match)
        updated["rerank_score"] = score
        updated["lexical_score"] = updated_lexical_score
        reranked.append(updated)

    return sorted(reranked, key=lambda item: item.get("rerank_score", item.get("score", 0)), reverse=True)


def summarize_coverage(
    raw_count: int,
    deduped_count: int,
    matches: List[Dict[str, Any]],
    plan: RetrievalPlan,
    budget_trimmed_count: int = 0,
) -> Dict[str, Any]:
    documents = {
        match.get("metadata", {}).get("source_file", "unknown")
        for match in matches
    }
    sections = {
        (
            match.get("metadata", {}).get("source_file", "unknown"),
            match.get("metadata", {}).get("section_path", "unknown"),
        )
        for match in matches
    }
    versions = {
        match.get("metadata", {}).get("version", "unknown")
        for match in matches
    }
    scores = [match.get("score", 0) for match in matches]
    best_score = max(scores) if scores else 0
    average_score = sum(scores) / len(scores) if scores else 0

    return {
        "mode": plan.mode,
        "reason": plan.reason,
        "requested_top_k": plan.top_k,
        "raw_evidence_count": raw_count,
        "deduped_evidence_count": deduped_count,
        "final_evidence_count": len(matches),
        "unique_evidence_count": len(matches),
        "duplicates_removed": max(raw_count - deduped_count, 0),
        "budget_trimmed_count": max(budget_trimmed_count, 0),
        "document_count": len(documents),
        "section_count": len(sections),
        "versions": sorted(str(version) for version in versions),
        "best_score": best_score,
        "average_score": average_score,
        "low_confidence": bool(scores) and best_score < 0.45 and plan.mode != "summary",
    }


def trim_matches_by_budget(matches: List[Dict[str, Any]], max_chars: int = 60000) -> List[Dict[str, Any]]:
    """Keep evidence within a simple prompt budget while preserving order."""
    return trim_matches_by_budget_with_count(matches, max_chars=max_chars)[0]


def trim_matches_by_budget_with_count(
    matches: List[Dict[str, Any]],
    max_chars: int = 60000,
) -> tuple[List[Dict[str, Any]], int]:
    """Keep evidence within budget and report how many matches were removed."""
    trimmed = []
    used_chars = 0
    for index, match in enumerate(matches):
        content = match.get("content", "")
        content_len = len(content)
        remaining = max_chars - used_chars
        if content_len > remaining:
            if not trimmed and max_chars > 0:
                truncated = dict(match)
                truncated_metadata = dict(match.get("metadata", {}))
                truncated_metadata["content_truncated"] = True
                truncated_metadata["original_content_chars"] = content_len
                truncated["metadata"] = truncated_metadata
                truncated["content"] = content[:max_chars]
                trimmed.append(truncated)
                return trimmed, len(matches) - index - 1
            return trimmed, len(matches) - index
        if used_chars + content_len > max_chars:
            break
        trimmed.append(match)
        used_chars += content_len
    return trimmed, max(len(matches) - len(trimmed), 0)


def order_matches_for_prompt(matches: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
    if mode != "summary":
        return matches
    return sorted(
        matches,
        key=lambda item: (
            str(item.get("metadata", {}).get("source_file", "")),
            str(item.get("metadata", {}).get("section_path", "")),
            str(item.get("metadata", {}).get("chunk_type", "")),
        ),
    )


def expand_parent_child_context(
    matches: List[Dict[str, Any]],
    context_pool: List[Dict[str, Any]],
    max_added: int = 20,
) -> List[Dict[str, Any]]:
    """Add parent/sibling chunks for matched child evidence."""
    if not matches or not context_pool:
        return matches

    by_chunk_id = {item.get("chunk_id"): item for item in context_pool}
    by_parent_id: Dict[str, List[Dict[str, Any]]] = {}
    for item in context_pool:
        metadata = item.get("metadata", {})
        parent_id = metadata.get("parent_id") or item.get("chunk_id")
        if parent_id:
            by_parent_id.setdefault(parent_id, []).append(item)

    expanded = list(matches)
    seen = {item.get("chunk_id") for item in expanded}
    added = 0
    for match in matches:
        metadata = match.get("metadata", {})
        parent_id = metadata.get("parent_id") or match.get("chunk_id")
        candidates = []
        if parent_id in by_chunk_id:
            candidates.append(by_chunk_id[parent_id])
        candidates.extend(by_parent_id.get(parent_id, []))
        for candidate in candidates:
            chunk_id = candidate.get("chunk_id")
            if not chunk_id or chunk_id in seen:
                continue
            enriched = dict(candidate)
            enriched["context_added"] = True
            enriched.setdefault("score", match.get("score", 0))
            expanded.append(enriched)
            seen.add(chunk_id)
            added += 1
            if added >= max_added:
                return expanded
    return expanded
