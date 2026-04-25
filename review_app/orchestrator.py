"""Review App - Orchestrator.

Coordinates the workflow:
1. Parse Query (User Query Parser)
2. Parse Input File (User Input File Parser) - if provided
3. Retrieve Evidence (from Vector Store)
4. Analyze (based on task type)
"""
from typing import Optional
from shared.models import (
    ParsedQuery, ParsedFile, Evidence, AnalysisResult, TaskType
)
from shared.llm import LLMProvider
from review_app.parsers.query_parser import UserQueryParser
from review_app.parsers.rag_input_file_parser import UserInputFileParser
from rag_app.vector_store import VectorStore


class Orchestrator:
    """Orchestrates the RAG workflow."""
    
    def __init__(self, llm: LLMProvider, vector_store: VectorStore):
        self.llm = llm
        self.vector_store = vector_store
        
        # Initialize parsers
        self.query_parser = UserQueryParser(llm)
        self.file_parser = UserInputFileParser()
    
    async def orchestrate(
        self,
        query: str,
        domain_id: str,
        input_file_path: Optional[str] = None
    ) -> AnalysisResult:
        """
        Orchestrate the full workflow:
        
        User Query → Parse Query → Orchestrator → Final Synthesis
        Input File → Parse Input ──┘
        """
        # Step 1: Parse user query
        parsed_query = await self.query_parser.parse(
            query, 
            has_input_file=bool(input_file_path)
        )
        
        # Step 2: Parse input file if provided
        parsed_file = None
        if input_file_path:
            from pathlib import Path
            parsed_file = await self.file_parser.parse(Path(input_file_path))
        
        # Step 3: Retrieve evidence from vector store
        matches = self.vector_store.search(
            query=parsed_query.reformulated_query or query,
            domain_id=domain_id,
            top_k=8,
            active_only=True,
        )
        
        evidence = [
            Evidence(
                chunk_id=m["chunk_id"],
                content=m["content"],
                source_file=m["metadata"].get("source_file", "unknown"),
                relevance_score=m["score"],
                section_path=m["metadata"].get("section_path"),
                source_page=m["metadata"].get("source_page") or None,
            )
            for m in matches
        ]
        
        # Step 4: Analyze based on task type
        analysis = await self._analyze(
            parsed_query=parsed_query,
            evidence=evidence,
            parsed_file=parsed_file
        )
        
        return AnalysisResult(
            task_type=parsed_query.intent,
            evidence=evidence,
            analysis=analysis,
            confidence=parsed_query.confidence
        )
    
    async def _analyze(
        self,
        parsed_query: ParsedQuery,
        evidence: list,
        parsed_file: Optional[ParsedFile]
    ) -> str:
        """Perform analysis based on task type."""
        evidence_text = "\n\n---\n\n".join([
            f"[Source: {e.source_file}]\n{e.content}" for e in evidence
        ])
        
        if parsed_query.intent == TaskType.VALIDATION and parsed_file:
            # Validation task
            system = """You are a compliance validator. Check the input against rules.
Identify violations and compliance status."""
            user = f"""Rules:\n{evidence_text}\n\n---\n\nInput to validate:\n{parsed_file.content}\n\nQuery: {parsed_query.original_query}"""
        
        elif parsed_query.intent == TaskType.ANALYSIS:
            # Analysis task
            system = """You are a business analyst. Analyze the rules and provide insights."""
            user = f"""Rules:\n{evidence_text}\n\n---\n\nAnalysis request: {parsed_query.original_query}"""
        
        else:
            # Q&A task
            system = """You are a business rule expert. Answer based on provided rules."""
            user = f"""Rules:\n{evidence_text}\n\n---\n\nQuestion: {parsed_query.original_query}"""
        
        messages = self.llm.format_messages(system, user)
        response = await self.llm.complete(messages, temperature=0.1)
        
        return response.content
