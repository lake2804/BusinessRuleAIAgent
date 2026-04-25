"""RAG App - Business Rule File Parser.

Parses business rule files to build knowledge base.
This is SEPARATE from user input file parser.
"""
import csv
import json
import re
import uuid
from pathlib import Path
from typing import Dict, List, Tuple


class BusinessRuleFileParser:
    """Parses business rule documents (policies, procedures, etc.)."""
    
    def parse(self, file_path: Path) -> Tuple[str, List[Dict]]:
        """Parse business rule file and return text + chunks."""
        suffix = file_path.suffix.lower()
        
        # Extract raw text
        if suffix == ".pdf":
            text, page_map = self._parse_pdf(file_path)
        elif suffix == ".docx":
            text = self._parse_docx(file_path)
            page_map = {}
        elif suffix == ".csv":
            text = self._parse_csv(file_path)
            page_map = {}
        elif suffix == ".json":
            text = self._parse_json(file_path)
            page_map = {}
        else:
            text = self._parse_text(file_path)
            page_map = {}
        
        # Chunk the content
        chunks = self._chunk_document(text, file_path.name, page_map=page_map)
        
        return text, chunks
    
    def _parse_pdf(self, file_path: Path) -> Tuple[str, Dict[str, int]]:
        """Extract text from PDF."""
        try:
            import pypdf
            text_parts = []
            page_map = {}
            with open(file_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                for page_num, page in enumerate(reader.pages, 1):
                    text = page.extract_text()
                    if text:
                        page_marker = f"--- Page {page_num} ---"
                        text_parts.append(f"{page_marker}\n{text}")
                        page_map[page_marker] = page_num
            return "\n".join(text_parts), page_map
        except Exception as exc:
            raise ValueError(f"PDF parsing error: {exc}") from exc
    
    def _parse_docx(self, file_path: Path) -> str:
        """Extract text from DOCX."""
        try:
            import docx
            doc = docx.Document(file_path)
            return "\n\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception as exc:
            raise ValueError(f"DOCX parsing error: {exc}") from exc
    
    def _parse_text(self, file_path: Path) -> str:
        """Read text file."""
        try:
            return file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            return file_path.read_text(encoding='latin-1')

    def _parse_csv(self, file_path: Path) -> str:
        """Convert CSV rows into readable text for retrieval."""
        try:
            with open(file_path, newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        except UnicodeDecodeError:
            with open(file_path, newline="", encoding="latin-1") as f:
                rows = list(csv.DictReader(f))

        if not rows:
            return self._parse_text(file_path)

        text_parts = [f"# CSV Data: {file_path.name}"]
        for row_num, row in enumerate(rows, 1):
            values = [f"{key}: {value}" for key, value in row.items() if value not in (None, "")]
            text_parts.append(f"## Row {row_num}\n" + "\n".join(values))
        return "\n\n".join(text_parts)

    def _parse_json(self, file_path: Path) -> str:
        """Pretty-print JSON into stable text for retrieval."""
        try:
            raw_text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw_text = file_path.read_text(encoding="latin-1")

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON parsing error: {exc}") from exc

        return f"# JSON Data: {file_path.name}\n\n" + json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    
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
        
        return self._preserve_table_sections(parts)

    def _looks_like_table_row(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if stripped.count("|") >= 2:
            return True
        columns = re.split(r"\s{2,}", stripped)
        return len([column for column in columns if column]) >= 4

    def _preserve_table_sections(self, sections: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Split table-like blocks into their own sections."""
        preserved = []
        for section_title, section_content in sections:
            lines = section_content.splitlines()
            text_buffer = []
            table_buffer = []
            table_count = 1

            def flush_text():
                if text_buffer:
                    preserved.append((section_title, "\n".join(text_buffer).strip()))
                    text_buffer.clear()

            def flush_table():
                nonlocal table_count
                if table_buffer:
                    preserved.append(
                        (
                            f"{section_title} > Table {table_count}",
                            "\n".join(table_buffer).strip(),
                        )
                    )
                    table_buffer.clear()
                    table_count += 1

            for line in lines:
                if self._looks_like_table_row(line):
                    flush_text()
                    table_buffer.append(line)
                else:
                    flush_table()
                    text_buffer.append(line)

            flush_table()
            flush_text()

        return [(title, content) for title, content in preserved if content]
    
    def _infer_page(self, content: str, page_map: Dict[str, int]) -> int | None:
        for page_marker, page_num in page_map.items():
            if page_marker in content:
                return page_num
        return None

    def _chunk_document(self, text: str, source_file: str,
                        parent_size: int = 2000, child_size: int = 500,
                        page_map: Dict[str, int] | None = None) -> List[Dict]:
        """Create parent-child chunks."""
        chunks = []
        page_map = page_map or {}
        sections = self._split_by_headings(text)
        
        for section_title, section_content in sections:
            parent_id = str(uuid.uuid4())
            source_page = self._infer_page(section_content, page_map)
            
            # Small section: single chunk
            if len(section_content) <= child_size * 2:
                chunks.append({
                    "chunk_id": parent_id,
                    "parent_id": None,
                    "chunk_type": "parent",
                    "content": section_content,
                    "section_path": section_title,
                    "source_file": source_file,
                    "source_page": source_page,
                })
                continue
            
            # Large section: parent + children
            chunks.append({
                "chunk_id": parent_id,
                "parent_id": None,
                "chunk_type": "parent",
                "content": section_content[:parent_size],
                "section_path": section_title,
                "source_file": source_file,
                "source_page": source_page,
            })
            
            # Child chunks
            position = 0
            chunk_num = 1
            overlap = 50
            
            while position < len(section_content):
                end_pos = min(position + child_size, len(section_content))
                child_content = section_content[position:end_pos]
                chunks.append({
                    "chunk_id": str(uuid.uuid4()),
                    "parent_id": parent_id,
                    "chunk_type": "child",
                    "content": child_content,
                    "section_path": f"{section_title} > Chunk {chunk_num}",
                    "source_file": source_file,
                    "source_page": self._infer_page(child_content, page_map) or source_page,
                })
                position += child_size - overlap
                chunk_num += 1
                
                if position >= len(section_content) - overlap:
                    break
        
        return chunks
