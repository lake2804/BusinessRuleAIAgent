"""RAG App - Component 4: Final Synthesis.

Combines all intermediate results into final output.
"""
from shared.models import (
    ParsedQuery, ParsedFile, Evidence, AnalysisResult, FinalResult
)
from shared.llm import LLMProvider


class FinalSynthesis:
    """Synthesizes final output from all components."""
    
    def __init__(self, llm: LLMProvider = None):
        self.llm = llm
    
    async def synthesize(
        self,
        query: str,
        parsed_query: ParsedQuery,
        parsed_file: Optional[ParsedFile],
        analysis_result: AnalysisResult
    ) -> FinalResult:
        """
        Synthesize final output from:
        - Parsed query (intent, entities)
        - Parsed file (if any)
        - Evidence (retrieved rules)
        - Analysis (intermediate analysis)
        """
        evidence = analysis_result.evidence
        analysis = analysis_result.analysis
        
        # Determine confidence level
        if len(evidence) >= 5 and analysis_result.confidence >= 0.8:
            confidence = "high"
        elif len(evidence) >= 3 and analysis_result.confidence >= 0.5:
            confidence = "medium"
        else:
            confidence = "low"
        
        # Build final output
        # Option 1: Direct use of analysis (simple)
        final_output = analysis
        
        # Option 2: LLM-based synthesis (if LLM available)
        if self.llm:
            final_output = await self._llm_synthesize(
                query, parsed_query, evidence, analysis
            )
        
        return FinalResult(
            query=query,
            parsed_query=parsed_query,
            parsed_file=parsed_file,
            evidence=evidence,
            analysis=analysis,
            final_output=final_output,
            confidence=confidence
        )
    
    async def _llm_synthesize(
        self,
        query: str,
        parsed_query: ParsedQuery,
        evidence: list,
        analysis: str
    ) -> str:
        """Use LLM to synthesize polished final output."""
        sources = list(set([e.source_file for e in evidence[:3]]))
        
        system = """You are a professional assistant. Synthesize a clear, structured response.
Include: direct answer, supporting evidence summary, and sources."""
        
        user = f"""Query: {query}
Intent: {parsed_query.intent.value}

Analysis:
{analysis}

Sources: {', '.join(sources)}

Synthesize a polished final response."""
        
        messages = self.llm.format_messages(system, user)
        response = await self.llm.complete(messages, temperature=0.2)
        
        return response.content
