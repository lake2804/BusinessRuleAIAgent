"""RAG App - Component 1: User Query Parser.

Parses user query to determine intent and extract entities.
"""
from shared.models import ParsedQuery, TaskType
from shared.llm import LLMProvider


class UserQueryParser:
    """Parses user queries to determine intent."""
    
    def __init__(self, llm: LLMProvider = None):
        self.llm = llm
    
    async def parse(self, query: str, has_input_file: bool = False) -> ParsedQuery:
        """Parse user query and determine intent."""
        query_lower = query.lower()
        
        # Rule-based intent detection
        if any(word in query_lower for word in ["validate", "check", "compliance", "verify", "does this comply"]):
            intent = TaskType.VALIDATION
            confidence = 0.95
        elif any(word in query_lower for word in ["analyze", "compare", "difference", "pattern", "trend"]):
            intent = TaskType.ANALYSIS
            confidence = 0.9
        elif any(word in query_lower for word in ["what", "how", "when", "where", "who", "why", "?"]):
            intent = TaskType.QNA
            confidence = 0.85
        else:
            intent = TaskType.QNA
            confidence = 0.7
        
        # If has input file and not explicitly validation, boost to validation
        if has_input_file and intent == TaskType.QNA:
            intent = TaskType.VALIDATION
            confidence = 0.8
        
        # Extract entities using LLM if available
        entities = {}
        if self.llm:
            entities = await self._extract_entities(query)
        
        return ParsedQuery(
            original_query=query,
            intent=intent,
            confidence=confidence,
            entities=entities,
            reformulated_query=query  # Can be enhanced with LLM
        )
    
    async def _extract_entities(self, query: str) -> dict:
        """Extract entities from query using LLM."""
        if not self.llm:
            return {}
        
        system = "Extract key entities (amounts, dates, categories) as JSON. Return {} if none."
        messages = self.llm.format_messages(system, f"Query: {query}")
        response = await self.llm.complete(messages, temperature=0.0, max_tokens=200)
        
        try:
            import json
            return json.loads(response.content)
        except:
            return {}
