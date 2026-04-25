"""Prompt and citation helpers for review workflows."""
from __future__ import annotations

from typing import Any, Dict, List


ISSUE_TAXONOMY = {
    "missing_input": "Required input data is absent or incomplete.",
    "invalid_or_unsupported_input": "An input value is present but not supported by the evidenced rule domain.",
    "evidence_gap": "The rule evidence is insufficient for a firm conclusion.",
    "hard_restriction": "A rule blocks final decisioning until a hold/approval is resolved.",
    "approval_path": "The case requires a specific owner, approver, or escalation route.",
    "rule_violation": "The input conflicts with an evidenced business rule.",
    "conditional_resolution": "A next-step or resolution is allowed only if stated conditions are met.",
}

GROUNDING_CHECKLIST = [
    "Return/refund condition directly cited, not inferred from case description.",
    "Numeric threshold or amount band directly cited before naming an approver from amount.",
    "Region validity directly cited before calling a value missing; otherwise unsupported.",
    "Owner/approver tied to the same scenario or explicitly applicable global rule.",
    "Evidence insufficiency separated from rule violation.",
]


def format_citations(matches: List[Dict[str, Any]]) -> List[str]:
    """Build stable, compact citation labels for prompt and UI display."""
    citations = []
    seen = set()
    citation_index = 1
    for match in matches:
        metadata = match.get("metadata", {})
        source = metadata.get("source_file", "unknown")
        section = metadata.get("section_path", "unknown")
        version = metadata.get("version", "unknown")
        page = metadata.get("source_page")
        key = (source, section, version, page)
        if key in seen:
            continue
        seen.add(key)
        page_text = f", page {page}" if page else ""
        citations.append(f"[S{citation_index}] {source}, {section}, v{version}{page_text}")
        citation_index += 1
    return citations


def format_evidence_for_prompt(matches: List[Dict[str, Any]]) -> str:
    blocks = []
    for index, match in enumerate(matches, 1):
        metadata = match.get("metadata", {})
        page = metadata.get("source_page")
        page_text = f"; Page: {page}" if page else ""
        blocks.append(
            (
                f"[S{index}] Source: {metadata.get('source_file', 'unknown')}; "
                f"Section: {metadata.get('section_path', 'unknown')}; "
                f"Version: {metadata.get('version', 'unknown')}{page_text}; "
                f"Score: {match.get('score', 0):.3f}\n"
                f"{match.get('content', '')}"
            )
        )
    return "\n\n---\n\n".join(blocks)


def build_validation_messages(evidence_text: str, input_content: str, query: str) -> tuple[str, str]:
    taxonomy_text = "\n".join(
        [f"- {name}: {description}" for name, description in ISSUE_TAXONOMY.items()]
    )
    checklist_text = "\n".join([f"- {item}" for item in GROUNDING_CHECKLIST])
    system = f"""You are a corporate-grade business-rule validation agent.

Use only the provided rule evidence and parsed input. Do not invent rules.

Required behavior:
- Validate each input case independently. Do not apply a blocker to every case unless the cited rule explicitly says it is globally mandatory.
- Separate directly evidenced findings from tentative inferences.
- Never place tentative inference inside the final corrected resolution. Put it in an "Inference / Needs confirmation" field.
- Use evidence strength labels for every finding: direct_rule, derived_from_rule, or evidence_gap.
- A finding is direct_rule only when the cited evidence explicitly states the rule, owner, threshold, condition, or blocker.
- A finding is derived_from_rule when it is a reasonable operational interpretation but not explicitly stated in the cited evidence.
- A finding is evidence_gap when the evidence does not prove the rule or condition.
- Do not state numeric approval thresholds, amount bands, or authority limits as fact unless the cited evidence contains the exact numeric threshold or named band. Otherwise mark approval_path as evidence_gap or derived_from_rule.
- Do not state return/refund rules such as opened seal, buyer remorse, damaged item, or perishable exception as fact unless cited evidence directly states that condition.
- If a region value is unsupported, such as GLOBAL, write "invalid_or_unsupported_input" unless the cited evidence explicitly says it is missing. Do not convert unsupported values into missing input without direct evidence.
- Map owner/approver from the scenario-specific evidence. If owner evidence is missing or conflicts, write "owner unresolved" and cite the gap.
- Distinguish issue types using this taxonomy:
{taxonomy_text}
- A final decision is allowed only when no hard restriction, required missing input, or critical evidence gap remains.
- Keep citations compact using [S1], [S2], etc.

Before finalizing, check:
{checklist_text}

Output format:
1. Batch-level summary: counts by final_decision_allowed = yes/no/conditional, and counts by issue type.
2. Case validation table with columns:
   case_id, directly_evidenced_findings, issue_type, final_decision_allowed,
   proposed_corrected_resolution, required_owner_or_approver, evidence_strength,
   inference_or_needs_confirmation, citations.
3. Per-case notes only when needed, focused on blockers and next steps.
4. Grounding warnings: list any claims that are derived_from_rule or evidence_gap, especially threshold, owner, region, or return-condition claims.
5. Cited Sources list using the provided citation IDs.
"""
    user = f"""Rule evidence:
{evidence_text}

---

Parsed input:
{input_content}

---

User request:
{query}
"""
    return system, user


def build_summary_messages(evidence_text: str, query: str) -> tuple[str, str]:
    system = (
        "You are a business rule analyst. Summarize every unique section in the provided "
        "active business-rule evidence. Do not repeat duplicate content. For each section, "
        "include what the rule says, owners/actions/SLA when present, and source citations. "
        "Separate directly evidenced content from inferred interpretation."
    )
    user = f"Business rule evidence:\n{evidence_text}\n\n---\n\nUser request: {query}"
    return system, user


def build_qna_messages(evidence_text: str, query: str) -> tuple[str, str]:
    system = (
        "You are a business rule expert. Answer based only on the retrieved rules. "
        "If evidence is insufficient, say so clearly. Separate direct evidence from inference. "
        "Use compact citations like [S1]. Do not state thresholds, owners, region validity, "
        "or return/refund conditions as fact unless directly evidenced."
    )
    user = f"Rules:\n{evidence_text}\n\n---\n\nQuery: {query}"
    return system, user
