"""Prompt and citation helpers for review workflows."""
from __future__ import annotations

from typing import Any, Dict, List

from review_app.schema import review_json_schema_text


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
    for index, match in enumerate(matches, 1):
        metadata = match.get("metadata", {})
        source = metadata.get("source_file", "unknown")
        section = metadata.get("section_path", "unknown")
        version = metadata.get("version", "unknown")
        page = metadata.get("source_page")
        page_text = f", page {page}" if page is not None and page != "" else ""
        citations.append(f"[S{index}] {source}, {section}, v{version}{page_text}")
    return citations


def format_evidence_for_prompt(matches: List[Dict[str, Any]]) -> str:
    blocks = []
    for index, match in enumerate(matches, 1):
        metadata = match.get("metadata", {})
        page = metadata.get("source_page")
        page_text = f"; Page: {page}" if page is not None and page != "" else ""
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


def build_validation_messages(evidence_text: str, input_content: str, query: str, domain_id: str = "", domain_name: str = "") -> tuple[str, str]:
    domain_context = ""
    if domain_id:
        domain_context = f"\n\nIMPORTANT: All rule evidence below comes from the currently selected business-rule domain: domain_id='{domain_id}', domain_name='{domain_name}'. When the user asks about this domain or mentions it by name/ID, they are referring to THIS domain."
    taxonomy_text = "\n".join(
        [f"- {name}: {description}" for name, description in ISSUE_TAXONOMY.items()]
    )
    checklist_text = "\n".join([f"- {item}" for item in GROUNDING_CHECKLIST])
    system = f"""You are a corporate-grade business-rule validation agent.{domain_context}

Use only the provided rule evidence and parsed input. Do not invent rules.

Required behavior:
- If the parsed input is a document/handbook/policy file rather than row-based cases, perform file-level validation. Check whether the uploaded file is consistent with the retrieved active business-rule domain, whether it conflicts with active rules, whether required rule-document metadata appears present, and whether any claims are unsupported by the evidence.
- When the parsed input includes "Domain knowledge matches", explicitly compare the chat-uploaded file against the matched domain knowledge file(s). If match_type is exact_content_hash, state that the uploaded file is byte-identical to the matched active domain document before evaluating rule consistency. If the match is only by file name/stem, treat it as a likely counterpart and compare cautiously.
- "This file" or "these files" refers to the file(s) attached in the Review chat session, not every file in the knowledge domain.
- For file-level validation, create one case with case_id equal to the uploaded file name or "uploaded_file", and use findings for document-level issues.
- The human_summary must start with one of: "Compliant", "Not compliant", "Conditionally compliant", or "Insufficient evidence".
- Do not answer only "correctness cannot be determined" when rule evidence is provided. Instead, list what was checked, which points are directly supported, which points conflict, and which points remain evidence gaps.
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
- Return valid JSON only. Do not wrap it in Markdown.
- If the user asks to correct or reformat an input file, populate corrected_records with rows/objects that satisfy the cited business-rule requirements. Preserve original fields when they are already compliant, and add correction notes fields when needed.
- Never change a user value unless a cited direct_rule or clearly derived_from_rule supports the correction. If the correct value cannot be proven from evidence, keep the original value and add a needs_confirmation/correction_note field instead.
- If the input is too large or evidence is incomplete for any row/file, mark that row/file as final_decision_allowed="unknown" or "conditional"; do not produce a clean compliant verdict for unchecked content.
- IMPORTANT: Keep the human_summary field simple and readable. Use plain text only. NO MARKDOWN. No tables, no headers, no bold text, no italics. Use simple bullet points with hyphens (-) if needed. Keep sentences short and clear. Focus on being direct and concise.

Before finalizing, check:
{checklist_text}

JSON schema:
{review_json_schema_text()}
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


def build_summary_messages(evidence_text: str, query: str, domain_id: str = "", domain_name: str = "") -> tuple[str, str]:
    domain_context = ""
    if domain_id:
        domain_context = f" All evidence below comes from the currently selected domain: domain_id='{domain_id}', domain_name='{domain_name}'."
    system = (
        f"You are a business rule analyst.{domain_context} Summarize every unique section in the provided "
        "active business-rule evidence. Do not repeat duplicate content. For each section, "
        "include what the rule says, owners/actions/SLA when present, and source citations. "
        "Separate directly evidenced content from inferred interpretation. "
        "CRITICAL: Format your response as simple plain text. NO MARKDOWN. No tables, no headers, "
        "no bold text, no italics. Use simple bullet points with hyphens (-) for lists. "
        "Keep sentences short and clear. Focus on being direct and concise."
    )
    user = f"Business rule evidence:\n{evidence_text}\n\n---\n\nUser request: {query}"
    return system, user


def build_qna_messages(evidence_text: str, query: str, domain_id: str = "", domain_name: str = "") -> tuple[str, str]:
    domain_context = ""
    if domain_id:
        domain_context = f" All evidence below comes from the currently selected domain: domain_id='{domain_id}', domain_name='{domain_name}'."
    system = (
        f"You are a business rule expert.{domain_context} Answer based only on the retrieved rules. "
        "If evidence is insufficient, say so clearly. Separate direct evidence from inference. "
        "Use compact citations like [S1]. Do not state thresholds, owners, region validity, "
        "or return/refund conditions as fact unless directly evidenced. "
        "\n\nCRITICAL FORMATTING RULES:\n"
        "- DO NOT USE ANY MARKDOWN SYNTAX\n"
        "- NO asterisks (*) for bold or italics\n"
        "- NO hash symbols (#) for headers\n"
        "- NO pipe symbols (|) for tables\n"
        "- NO brackets [] for emphasis (except for citations like [S1])\n"
        "- Write like a normal text message or email\n"
        "- Use simple bullet points with hyphens (-) only when listing multiple items\n"
        "- Keep paragraphs short (2-3 sentences max)\n"
        "- Example of GOOD format:\n"
        "The policy covers refund decisions. Key rules include:\n"
        "- Default to least costly option [S1]\n"
        "- Requires approval for holds [S2]\n"
        "- Regional overrides apply when valid [S3]\n"
        "\nExample of BAD format:\n"
        "**Policy Rules**\n"
        "| Rule | Source |\n"
        "|------|--------|\n"
        "| Default option | [S1] |\n"
    )
    user = f"Rules:\n{evidence_text}\n\n---\n\nQuery: {query}\n\nRemember: NO MARKDOWN - plain text only!"
    return system, user


def build_json_repair_messages(response_text: str, validation_error: str) -> tuple[str, str]:
    system = (
        "You repair model output into valid JSON. Return valid JSON only, with no Markdown. "
        "Do not add new facts. Preserve the original meaning while matching the schema."
    )
    user = f"""Schema:
{review_json_schema_text()}

Validation error:
{validation_error}

Original response:
{response_text}
"""
    return system, user
