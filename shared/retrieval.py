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

VALIDATION_TERMS = ["validate", "check", "comply", "compliance", "verify"]
ANALYSIS_TERMS = ["analyze", "compare", "difference", "trend", "pattern"]


@dataclass(frozen=True)
class RetrievalPlan:
    mode: str
    top_k: int
    use_full_domain: bool
    score_threshold: float | None
    reason: str


def detect_query_mode(query: str, has_input_file: bool = False) -> str:
    query_lower = query.lower()
    if any(term in query_lower for term in SUMMARY_TERMS):
        return "summary"
    if has_input_file or any(term in query_lower for term in VALIDATION_TERMS):
        return "validation"
    if any(term in query_lower for term in ANALYSIS_TERMS):
        return "analysis"
    return "qna"


def plan_retrieval(query: str, has_input_file: bool = False) -> RetrievalPlan:
    mode = detect_query_mode(query, has_input_file=has_input_file)
    word_count = len(re.findall(r"\w+", query))

    if mode == "summary":
        return RetrievalPlan(
            mode=mode,
            top_k=200,
            use_full_domain=True,
            score_threshold=None,
            reason="Broad summary request; reviewing all active domain evidence.",
        )

    if mode == "validation":
        return RetrievalPlan(
            mode=mode,
            top_k=24 if word_count > 20 else 18,
            use_full_domain=False,
            score_threshold=0.12,
            reason="Validation request; retrieving a wider evidence set.",
        )

    if mode == "analysis":
        return RetrievalPlan(
            mode=mode,
            top_k=16 if word_count > 16 else 12,
            use_full_domain=False,
            score_threshold=0.18,
            reason="Analysis request; retrieving enough evidence for comparison.",
        )

    return RetrievalPlan(
        mode=mode,
        top_k=10 if word_count > 14 else 6,
        use_full_domain=False,
        score_threshold=0.22,
        reason="Focused Q&A request; retrieving the most relevant evidence.",
    )


def build_retrieval_query(query: str, mode: str, has_input_file: bool = False) -> str:
    """Expand broad validation queries with terms that improve rule coverage."""
    if mode != "validation":
        return query

    validation_terms = [
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
    file_hint = " parsed input file rows" if has_input_file else ""
    return f"{query}{file_hint}\n" + "\n".join(validation_terms)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _content_hash(text: str) -> str:
    return hashlib.sha256(_normalize_text(text).encode("utf-8")).hexdigest()


def deduplicate_matches(matches: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate evidence while keeping the highest-scoring copy."""
    best_by_key: Dict[tuple, Dict[str, Any]] = {}

    for match in matches:
        metadata = match.get("metadata", {})
        key = (
            metadata.get("document_id") or metadata.get("source_file") or "",
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

        if mode == "validation":
            validation_hits = sum(1 for term in validation_boost_terms if term in haystack)
            score += min(validation_hits * 0.02, 0.2)

        if metadata.get("active") is True or str(metadata.get("status", "")).lower() == "active":
            score += 0.05
        if str(metadata.get("status", "")).lower() == "archived":
            score -= 0.15

        updated = dict(match)
        updated["rerank_score"] = score
        reranked.append(updated)

    return sorted(reranked, key=lambda item: item.get("rerank_score", item.get("score", 0)), reverse=True)


def summarize_coverage(raw_count: int, matches: List[Dict[str, Any]], plan: RetrievalPlan) -> Dict[str, Any]:
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
        "unique_evidence_count": len(matches),
        "duplicates_removed": max(raw_count - len(matches), 0),
        "document_count": len(documents),
        "section_count": len(sections),
        "versions": sorted(str(version) for version in versions),
        "best_score": best_score,
        "average_score": average_score,
        "low_confidence": bool(scores) and best_score < 0.45 and plan.mode != "summary",
    }


def trim_matches_by_budget(matches: List[Dict[str, Any]], max_chars: int = 60000) -> List[Dict[str, Any]]:
    """Keep evidence within a simple prompt budget while preserving order."""
    trimmed = []
    used_chars = 0
    for match in matches:
        content_len = len(match.get("content", ""))
        if trimmed and used_chars + content_len > max_chars:
            break
        trimmed.append(match)
        used_chars += content_len
    return trimmed


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
