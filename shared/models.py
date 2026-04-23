"""Shared models."""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    QNA = "qna"
    VALIDATION = "validation"
    ANALYSIS = "analysis"


class Domain(BaseModel):
    domain_id: str
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ParsedQuery(BaseModel):
    """Result from User Query Parser."""
    original_query: str
    intent: TaskType
    confidence: float
    entities: Dict[str, Any] = Field(default_factory=dict)
    reformulated_query: Optional[str] = None


class ParsedFile(BaseModel):
    """Result from Input File Parser."""
    file_name: str
    file_type: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    """Evidence from RAG search."""
    chunk_id: str
    content: str
    source_file: str
    relevance_score: float
    section_path: Optional[str] = None


class AnalysisResult(BaseModel):
    """Result from analysis step."""
    task_type: TaskType
    evidence: List[Evidence]
    analysis: str
    confidence: float


class FinalResult(BaseModel):
    """Final output from synthesis."""
    query: str
    parsed_query: ParsedQuery
    parsed_file: Optional[ParsedFile] = None
    evidence: List[Evidence]
    analysis: str
    final_output: str
    confidence: str
    processing_time_ms: Optional[float] = None
