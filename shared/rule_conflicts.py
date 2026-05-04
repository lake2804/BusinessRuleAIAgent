"""Lightweight rule conflict detection for newly ingested chunks."""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, List

from shared.rule_metadata import extract_rule_metadata


def detect_rule_conflicts(
    new_chunks: List[Dict[str, Any]],
    existing_matches: List[Dict[str, Any]],
    similarity_threshold: float = 0.55,
) -> List[Dict[str, Any]]:
    """Flag same-section or same-concept chunks whose content appears materially different."""
    conflicts = []
    existing_by_section: Dict[str, List[Dict[str, Any]]] = {}
    existing_by_concept: Dict[tuple, List[Dict[str, Any]]] = {}
    for match in existing_matches:
        metadata = match.get("metadata", {})
        section = str(metadata.get("section_path", ""))
        existing_by_section.setdefault(section, []).append(match)
        concept = (
            metadata.get("region", ""),
            metadata.get("scenario", ""),
            metadata.get("rule_type", ""),
        )
        if any(concept):
            existing_by_concept.setdefault(concept, []).append(match)

    for chunk in new_chunks:
        section = str(chunk.get("section_path", ""))
        new_metadata = extract_rule_metadata(chunk.get("content", ""), section)
        concept = (
            new_metadata.get("region", ""),
            new_metadata.get("scenario", ""),
            new_metadata.get("rule_type", ""),
        )
        candidates = list(existing_by_section.get(section, []))
        candidates.extend(existing_by_concept.get(concept, []))
        seen_ids = set()
        for existing in candidates:
            existing_id = existing.get("chunk_id") or id(existing)
            if existing_id in seen_ids:
                continue
            seen_ids.add(existing_id)
            old_content = existing.get("content", "")
            new_content = chunk.get("content", "")
            if not old_content or not new_content or old_content == new_content:
                continue
            similarity = SequenceMatcher(None, old_content, new_content).ratio()
            if similarity < similarity_threshold:
                conflicts.append(
                    {
                        "section_path": section,
                        "existing_source": existing.get("metadata", {}).get("source_file", "unknown"),
                        "existing_version": existing.get("metadata", {}).get("version", "unknown"),
                        "conflict_basis": "section" if existing in existing_by_section.get(section, []) else "concept",
                        "similarity": round(similarity, 3),
                    }
                )
    return conflicts
