"""RAG App - Component 2: User Input File Parser.

Parses files uploaded by users for validation/analysis.
"""
from pathlib import Path
from typing import Optional
from shared.models import ParsedFile


class UserInputFileParser:
    """Parses user input files (invoices, forms, etc.) for validation."""
    
    async def parse(self, file_path: Path) -> Optional[ParsedFile]:
        """Parse user input file and extract content."""
        suffix = file_path.suffix.lower()
        
        if suffix == ".pdf":
            return await self._parse_pdf(file_path)
        elif suffix == ".docx":
            return await self._parse_docx(file_path)
        elif suffix in [".txt", ".md", ".csv"]:
            return await self._parse_text(file_path)
        else:
            return ParsedFile(
                file_name=file_path.name,
                file_type=suffix,
                content=f"[Unsupported file type: {suffix}]",
                metadata={"error": "unsupported_type"}
            )
    
    async def _parse_pdf(self, file_path: Path) -> ParsedFile:
        """Parse PDF file."""
        try:
            import pypdf
            text_parts = []
            
            with open(file_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                for page_num, page in enumerate(reader.pages, 1):
                    text = page.extract_text()
                    if text:
                        text_parts.append(f"--- Page {page_num} ---\n{text}")
            
            return ParsedFile(
                file_name=file_path.name,
                file_type="pdf",
                content="\n\n".join(text_parts),
                metadata={"pages": len(reader.pages)}
            )
        except Exception as e:
            return ParsedFile(
                file_name=file_path.name,
                file_type="pdf",
                content=f"[PDF parse error: {str(e)}]",
                metadata={"error": str(e)}
            )
    
    async def _parse_docx(self, file_path: Path) -> ParsedFile:
        """Parse Word document."""
        try:
            import docx
            doc = docx.Document(file_path)
            
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            
            return ParsedFile(
                file_name=file_path.name,
                file_type="docx",
                content="\n\n".join(paragraphs),
                metadata={"paragraphs": len(paragraphs)}
            )
        except Exception as e:
            return ParsedFile(
                file_name=file_path.name,
                file_type="docx",
                content=f"[DOCX parse error: {str(e)}]",
                metadata={"error": str(e)}
            )
    
    async def _parse_text(self, file_path: Path) -> ParsedFile:
        """Parse text file."""
        try:
            content = file_path.read_text(encoding='utf-8')
            return ParsedFile(
                file_name=file_path.name,
                file_type=file_path.suffix.lstrip('.'),
                content=content,
                metadata={"size_bytes": file_path.stat().st_size}
            )
        except UnicodeDecodeError:
            # Try with latin-1
            content = file_path.read_text(encoding='latin-1')
            return ParsedFile(
                file_name=file_path.name,
                file_type=file_path.suffix.lstrip('.'),
                content=content,
                metadata={"encoding": "latin-1"}
            )
