"""Query Parser - Intent understanding layer for review workflow.

This module parses user queries to determine intent and extract entities.
It decides what the user is asking:
- Validate compliance?
- Summarize business rules?
- Correct/reshape an uploaded file?
- Export in a specific format?
- Compare uploaded files with domain knowledge?
- Inspect evidence/citations?
- Ask normal Q&A?
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from shared.llm import LLMProvider


@dataclass
class ParsedQuery:
    """Result of parsing a user query."""
    original_query: str
    intent: str  # validation, summary, analysis, qna, export, compare, inspect
    confidence: float
    entities: Dict[str, Any] = field(default_factory=dict)
    reformulated_query: str = ""
    # Mode-specific flags
    wants_export: bool = False
    export_formats: List[str] = field(default_factory=list)
    wants_correction: bool = False
    wants_comparison: bool = False
    wants_evidence_inspection: bool = False
    
    def __post_init__(self):
        if not self.reformulated_query:
            self.reformulated_query = self.original_query


# Intent detection patterns
VALIDATION_TERMS: Set[str] = {
    "validate", "validation", "check", "correct", "comply", "complies",
    "complying", "compliance", "verify", "valid", "does this comply",
    "is this valid", "are these valid", "check if", "validate this"
}

SUMMARY_TERMS: Set[str] = {
    "summarize", "summary", "overview", "go through", "tell me detail",
    "tell me everything", "what is mentioned", "summarize all",
    "all business rule", "entire business rule", "full summary"
}

ANALYSIS_TERMS: Set[str] = {
    "analyze", "analysis", "compare", "comparison", "difference",
    "trend", "pattern", "contrast", "versus", "vs"
}

EXPORT_TERMS: Set[str] = {
    "export", "download", "save as", "output as", "convert to",
    "give me a csv", "give me an excel", "spreadsheet", "xlsx", "csv"
}

CORRECTION_TERMS: Set[str] = {
    "correct", "fix", "repair", "reshape", "reformat", "clean up",
    "make this compliant", "fix this", "correct this"
}

INSPECTION_TERMS: Set[str] = {
    "show evidence", "show citations", "what rules", "which rules",
    "source of", "where does it say", "citation", "reference"
}

COMPARISON_TERMS: Set[str] = {
    "compare", "comparison", "difference between", "diff", "versus",
    "vs", "how does this compare", "contrast with"
}

QNA_TERMS: Set[str] = {
    "what", "how", "when", "where", "who", "why", "?"
}

FILE_REFERENCE_TERMS: Set[str] = {
    "this file", "the file", "uploaded file", "attached file",
    "following file", "this document", "the document"
}


def _matches_terms(query_lower: str, terms: Set[str]) -> bool:
    """Check if query matches any of the given terms."""
    for term in terms:
        if term in query_lower:
            return True
    return False


def _extract_export_formats(query: str) -> List[str]:
    """Extract requested export formats from query."""
    formats = []
    query_lower = query.lower()
    
    format_patterns = {
        "csv": ["csv", "spreadsheet"],
        "xlsx": ["xlsx", "excel", "spreadsheet"],
        "json": ["json"],
        "pdf": ["pdf"],
        "docx": ["docx", "word"],
        "md": ["md", "markdown"],
        "txt": ["txt", "text"],
    }
    
    for fmt, patterns in format_patterns.items():
        for pattern in patterns:
            if pattern in query_lower:
                formats.append(fmt)
                break
    
    return list(set(formats))  # Deduplicate


def _references_file(query: str) -> bool:
    """Check if query references a file without explicit upload."""
    query_lower = query.lower()
    return any(term in query_lower for term in FILE_REFERENCE_TERMS)


def _extract_entities_with_llm(llm: Optional[LLMProvider], query: str) -> Dict[str, Any]:
    """Use LLM to extract entities when available."""
    if not llm:
        return {}
    
    system = """Extract key entities from the query as JSON. Return an object with:
- amounts: list of monetary amounts mentioned
- dates: list of dates mentioned  
- regions: list of geographic regions mentioned
- categories: list of business categories/topics
- approval_thresholds: list of approval thresholds
- case_ids: list of case IDs or record identifiers
- actions: list of actions requested (validate, summarize, export, etc.)

Return {} if no entities found."""
    
    try:
        import asyncio
        messages = llm.format_messages(system, f"Query: {query}")
        # Note: This is a synchronous wrapper - caller should use async version
        response = asyncio.run(llm.complete(messages, temperature=0.0, max_tokens=300))
        import json
        return json.loads(response.content)
    except Exception:
        return {}


class QueryParser:
    """Parses user queries to determine intent and extract entities."""
    
    def __init__(self, llm: Optional[LLMProvider] = None):
        self.llm = llm
    
    async def parse(self, query: str, has_input_file: bool = False) -> ParsedQuery:
        """Parse user query and determine intent.
        
        Args:
            query: The user's query string
            has_input_file: Whether a file has been uploaded for context
            
        Returns:
            ParsedQuery with intent, confidence, and extracted entities
        """
        query_lower = query.lower()
        entities: Dict[str, Any] = {"original_terms": []}
        
        # Detect intent based on keyword matching
        intent_scores: Dict[str, float] = {}
        
        # Validation detection
        if _matches_terms(query_lower, VALIDATION_TERMS):
            if has_input_file or _references_file(query):
                intent_scores["validation"] = 0.95
            else:
                intent_scores["validation"] = 0.75
        
        # Summary detection
        if _matches_terms(query_lower, SUMMARY_TERMS):
            intent_scores["summary"] = 0.90
        
        # Analysis/Comparison detection
        if _matches_terms(query_lower, COMPARISON_TERMS):
            if has_input_file:
                intent_scores["comparison"] = 0.90
            else:
                intent_scores["analysis"] = 0.85
        elif _matches_terms(query_lower, ANALYSIS_TERMS):
            intent_scores["analysis"] = 0.85
        
        # Export detection
        if _matches_terms(query_lower, EXPORT_TERMS):
            intent_scores["export"] = 0.80
        
        # Correction detection
        if _matches_terms(query_lower, CORRECTION_TERMS):
            if has_input_file:
                intent_scores["correction"] = 0.88
            else:
                intent_scores["correction"] = 0.65
        
        # Evidence inspection
        if _matches_terms(query_lower, INSPECTION_TERMS):
            intent_scores["inspect"] = 0.85
        
        # Default QnA detection
        if _matches_terms(query_lower, QNA_TERMS):
            intent_scores["qna"] = 0.70
        
        # Default fallback
        if not intent_scores:
            intent_scores["qna"] = 0.60
        
        # Select highest scoring intent
        intent = max(intent_scores, key=intent_scores.get)
        confidence = intent_scores[intent]
        
        # Boost confidence for certain patterns
        if has_input_file and intent in ["validation", "comparison", "correction"]:
            confidence = min(confidence + 0.10, 1.0)
        
        # Extract additional flags
        wants_export = intent == "export" or _matches_terms(query_lower, EXPORT_TERMS)
        export_formats = _extract_export_formats(query) if wants_export else []
        
        wants_correction = intent == "correction" or (
            _matches_terms(query_lower, CORRECTION_TERMS) and has_input_file
        )
        
        wants_comparison = intent == "comparison" or (
            _matches_terms(query_lower, COMPARISON_TERMS) and has_input_file
        )
        
        wants_evidence_inspection = intent == "inspect" or _matches_terms(query_lower, INSPECTION_TERMS)
        
        # Extract entities using LLM if available
        if self.llm and confidence < 0.85:
            try:
                llm_entities = await self._extract_entities_async(query)
                entities.update(llm_entities)
            except Exception:
                pass
        
        # Reformulate query for better retrieval if needed
        reformulated = self._reformulate_query(query, intent)
        
        return ParsedQuery(
            original_query=query,
            intent=intent,
            confidence=confidence,
            entities=entities,
            reformulated_query=reformulated,
            wants_export=wants_export,
            export_formats=export_formats,
            wants_correction=wants_correction,
            wants_comparison=wants_comparison,
            wants_evidence_inspection=wants_evidence_inspection,
        )
    
    async def _extract_entities_async(self, query: str) -> Dict[str, Any]:
        """Async version of entity extraction."""
        if not self.llm:
            return {}
        
        system = """Extract key entities from the query as JSON. Return an object with optional fields:
- amounts: list of monetary amounts mentioned
- dates: list of dates mentioned  
- regions: list of geographic regions mentioned
- categories: list of business categories/topics
- approval_thresholds: list of approval thresholds
- case_ids: list of case IDs or record identifiers
- actions: list of actions requested

Return {} if no entities found. Only include fields where entities were found."""
        
        messages = self.llm.format_messages(system, f"Query: {query}")
        response = await self.llm.complete(messages, temperature=0.0, max_tokens=300)
        
        try:
            import json
            return json.loads(response.content)
        except Exception:
            return {}
    
    def _reformulate_query(self, query: str, intent: str) -> str:
        """Reformulate query for better retrieval based on intent."""
        # For validation queries, add context terms
        if intent == "validation":
            # Check if query needs more context
            if len(query.split()) < 5:
                return f"Validate compliance with business rules: {query}"
        
        # For summary queries, ensure we capture the scope
        if intent == "summary":
            if "all" not in query.lower() and "every" not in query.lower():
                return f"Summarize all business rules: {query}"
        
        return query
    
    def detect_mode(self, query: str, has_input_file: bool = False) -> str:
        """Quick mode detection for backward compatibility with retrieval.py.
        
        Returns: mode string (summary, validation, analysis, qna)
        """
        query_lower = query.lower()
        
        # Check summary terms first
        if _matches_terms(query_lower, SUMMARY_TERMS):
            return "summary"
        
        # Check validation terms
        if has_input_file or _matches_terms(query_lower, VALIDATION_TERMS):
            return "validation"
        
        # Check analysis terms
        if _matches_terms(query_lower, ANALYSIS_TERMS) or _matches_terms(query_lower, COMPARISON_TERMS):
            return "analysis"
        
        # Default to QnA
        return "qna"


# Convenience function for backward compatibility
def detect_query_mode(query: str, has_input_file: bool = False) -> str:
    """Backward compatible mode detection.
    
    This function provides the same interface as the original retrieval.py
    detect_query_mode function for backward compatibility.
    """
    parser = QueryParser()
    return parser.detect_mode(query, has_input_file)
