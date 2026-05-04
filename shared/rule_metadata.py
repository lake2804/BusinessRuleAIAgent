"""Heuristic metadata extraction for business-rule chunks."""
from __future__ import annotations

import re
from typing import Any, Dict


KNOWN_REGIONS = {"EU", "VN", "SG", "UAE", "US", "UK", "IN", "GLOBAL"}
KNOWN_OWNERS = [
    "Risk Ops",
    "Finance",
    "Compliance",
    "Ops",
    "Carrier team",
    "Tier2 Ops",
    "Regional Manager",
    "Finance Control Manager",
    "Supervisor",
]


def extract_rule_metadata(content: str, section_path: str = "") -> Dict[str, Any]:
    text = f"{section_path}\n{content}"
    upper = text.upper()
    metadata: Dict[str, Any] = {}

    regions = sorted(region for region in KNOWN_REGIONS if re.search(rf"\b{region}\b", upper))
    if regions:
        metadata["region"] = ",".join(regions)

    owners = [owner for owner in KNOWN_OWNERS if owner.lower() in text.lower()]
    if owners:
        metadata["owner"] = ",".join(sorted(set(owners)))

    rule_types = []
    lowered = text.lower()
    for term in ["approval", "threshold", "sla", "escalation", "override", "fraud", "refund", "evidence"]:
        if term in lowered:
            rule_types.append(term)
    if rule_types:
        metadata["rule_type"] = ",".join(rule_types)

    scenario_match = re.search(r"(changed payment destination|3\+ claims|legal withdrawal|delivered-not-received|damaged luxury item|fraud hold)", lowered)
    if scenario_match:
        metadata["scenario"] = scenario_match.group(1)

    date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if date_match:
        metadata["effective_date"] = date_match.group(1)

    return metadata
