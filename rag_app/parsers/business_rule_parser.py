"""RAG App - Business Rule File Parser.

Parses business rule files to build knowledge base.
This is SEPARATE from user input file parser.
"""
import re
import uuid
from pathlib import Path
from typing import List, Dict, Tuple


class BusinessRuleFileParser:
    """Parses business rule documents (policies, procedures, etc.)."""
    
    def parse(self, file_path: Path) -> Tuple[str, List[Dict]]:
        """Parse business rule file and return text + chunks."""
        suffix = file_path.suffix.lower()
        
        # Extract raw text
        if suffix == ".pdf":
            text = self._parse_pdf(file_path)
        elif suffix == ".docx":
            text = self._parse_docx(file_path)
        else:
            text = self._parse_text(file_path)
        
        # Chunk the content
        chunks = self._chunk_document(text, file_path.name)
        
        return text, chunks
    
    def _parse_pdf(self, file_path: Path) -> str:
        """Extract text from PDF."""
        try:
            import pypdf
            text_parts = []
            with open(file_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n".join(text_parts)
        except:
            return "[PDF parsing error]"
    
    def _parse_docx(self, file_path: Path) -> str:
        """Extract text from DOCX."""
        try:
            import docx
            doc = docx.Document(file_path)
            return "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except:
            return "[DOCX parsing error]"
    
    def _parse_text(self, file_path: Path) -> str:
        """Read text file."""
        try:
            return file_path.read_text(encoding='utf-8')
        except:
            return file_path.read_text(encoding='latin-1')
    
    def _split_by_headings(self, text: str) -> List[Tuple[str, str]]:
        """Split text by headings."""
        pattern = r'(?:\n|^)(?:\d+\.\s+|Section\s+\d+[.:]?\s*|#{1,3}\s+)([^\n]+)'
        
        parts = []
        last_end = 0
        current_heading = "Introduction"
        
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if match.start() > last_end:
                section_content = text[last_end:match.start()].strip()
                if section_content:
                    parts.append((current_heading, section_content))
            current_heading = match.group(1).strip()
            last_end = match.end()
        
        if last_end < len(text):
            final_content = text[last_end:].strip()
            if final_content:
                parts.append((current_heading, final_content))
        
        if not parts and text.strip():
            parts.append(("Document", text.strip()))
        
        return parts
    
    def _chunk_document(self, text: str, source_file: str,
                        parent_size: int = 2000, child_size: int = 500) -> List[Dict]:
        """Create parent-child chunks."""
        chunks = []
        sections = self._split_by_headings(text)
        
        for section_title, section_content in sections:
            parent_id = str(uuid.uuid4())
            
            # Small section: single chunk
            if len(section_content) <= child_size * 2:
                chunks.append({
                    "chunk_id": parent_id,
                    "parent_id": None,
                    "chunk_type": "parent",
                    "content": section_content,
                    "section_path": section_title,
                    "source_file": source_file
                })
                continue
            
            # Large section: parent + children
            chunks.append({
                "chunk_id": parent_id,
                "parent_id": None,
                "chunk_type": "parent",
                "content": section_content[:parent_size],
                "section_path": section_title,
                "source_file": source_file
            })
            
            # Child chunks
            position = 0
            chunk_num = 1
            overlap = 50
            
            while position < len(section_content):
                end_pos = min(position + child_size, len(section_content))
                chunks.append({
                    "chunk_id": str(uuid.uuid4()),
                    "parent_id": parent_id,
                    "chunk_type": "child",
                    "content": section_content[position:end_pos],
                    "section_path": f"{section_title} > Chunk {chunk_num}",
                    "source_file": source_file
                })
                position += child_size - overlap
                chunk_num += 1
                
                if position >= len(section_content) - overlap:
                    break
        
        return chunks
