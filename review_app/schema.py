"""Structured review output models and parsing helpers."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field, ValidationError


class ReviewFinding(BaseModel):
    case_id: str = ""
    issue_type: str
    finding: str
    evidence_strength: str = Field(pattern="^(direct_rule|derived_from_rule|evidence_gap)$")
    citations: List[str] = Field(default_factory=list)


class CaseValidationResult(BaseModel):
    case_id: str
    directly_evidenced_findings: List[str] = Field(default_factory=list)
    issue_types: List[str] = Field(default_factory=list)
    final_decision_allowed: str = Field(pattern="^(yes|no|conditional|unknown)$")
    proposed_corrected_resolution: str = ""
    required_owner_or_approver: str = ""
    evidence_strength: str = Field(default="evidence_gap")
    inference_or_needs_confirmation: str = ""
    citations: List[str] = Field(default_factory=list)
    corrected_record: Dict[str, Any] = Field(default_factory=dict)


class ReviewStructuredOutput(BaseModel):
    batch_summary: Dict[str, Any] = Field(default_factory=dict)
    cases: List[CaseValidationResult] = Field(default_factory=list)
    findings: List[ReviewFinding] = Field(default_factory=list)
    grounding_warnings: List[str] = Field(default_factory=list)
    cited_sources: List[str] = Field(default_factory=list)
    corrected_records: List[Dict[str, Any]] = Field(default_factory=list)
    human_summary: str = ""


def review_json_schema_text() -> str:
    """Compact schema instruction for the LLM prompt."""
    return json.dumps(ReviewStructuredOutput.model_json_schema(), indent=2)


def extract_json_object(text: str) -> Optional[str]:
    """Extract the first JSON object from a response."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1)

    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def parse_structured_review(text: str) -> tuple[Optional[ReviewStructuredOutput], Optional[str]]:
    """Parse validated structured output, returning an error message on failure."""
    json_text = extract_json_object(text)
    if not json_text:
        return None, "No JSON object found in model response."
    try:
        return ReviewStructuredOutput.model_validate(json.loads(json_text)), None
    except (json.JSONDecodeError, ValidationError) as exc:
        return None, str(exc)


def normalize_citation_id(citation: str) -> str:
    citation = citation.strip()
    if citation.startswith("[") and citation.endswith("]"):
        citation = citation[1:-1]
    return citation.upper()


def validate_structured_citations(
    structured_output: ReviewStructuredOutput,
    valid_citations: Iterable[str],
) -> List[str]:
    """Return invalid citations found in structured case/finding output."""
    valid = {normalize_citation_id(item) for item in valid_citations}
    invalid = []

    def check(citations: List[str], context: str):
        for citation in citations:
            normalized = normalize_citation_id(citation)
            if normalized and normalized not in valid:
                invalid.append(f"{context}: {citation}")

    for case in structured_output.cases:
        check(case.citations, f"case {case.case_id}")
    for finding in structured_output.findings:
        check(finding.citations, f"finding {finding.case_id or finding.issue_type}")
    return invalid
