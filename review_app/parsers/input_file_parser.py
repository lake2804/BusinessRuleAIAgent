"""Review App - User Input File Parser.

This is SEPARATE from RAG App's parsers.
Used for parsing user input files for validation.
"""
from pathlib import Path
from typing import Optional


class UserInputFileParser:
    """Parses user input files (invoices, forms, etc.) for validation."""
    
    async def parse(self, file_path: Path) -> Optional[dict]:
        """Parse user input file."""
        suffix = file_path.suffix.lower()
        
        if suffix == ".pdf":
            return await self._parse_pdf(file_path)
        elif suffix == ".docx":
            return await self._parse_docx(file_path)
        elif suffix in [".txt", ".md", ".csv"]:
            return await self._parse_text(file_path)
        else:
            return {
                "file_name": file_path.name,
                "file_type": suffix,
                "content": f"[Unsupported: {suffix}]",
                "metadata": {"error": "unsupported"}
            }
    
    async def _parse_pdf(self, file_path: Path) -> dict:
        try:
            import pypdf
            text_parts = []
            
            with open(file_path, 'rb') as f:
                reader = pypdf.PdfReader(f)
                for page_num, page in enumerate(reader.pages, 1):
                    text = page.extract_text()
                    if text:
                        text_parts.append(f"--- Page {page_num} ---\n{text}")
            
            return {
                "file_name": file_path.name,
                "file_type": "pdf",
                "content": "\n\n".join(text_parts),
                "metadata": {"pages": len(reader.pages)}
            }
        except Exception as e:
            return {
                "file_name": file_path.name,
                "file_type": "pdf",
                "content": f"[Error: {str(e)}]",
                "metadata": {"error": str(e)}
            }
    
    async def _parse_docx(self, file_path: Path) -> dict:
        try:
            import docx
            doc = docx.Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            
            return {
                "file_name": file_path.name,
                "file_type": "docx",
                "content": "\n\n".join(paragraphs),
                "metadata": {"paragraphs": len(paragraphs)}
            }
        except Exception as e:
            return {
                "file_name": file_path.name,
                "file_type": "docx",
                "content": f"[Error: {str(e)}]",
                "metadata": {"error": str(e)}
            }
    
    async def _parse_text(self, file_path: Path) -> dict:
        try:
            content = file_path.read_text(encoding='utf-8')
            return {
                "file_name": file_path.name,
                "file_type": file_path.suffix.lstrip('.'),
                "content": content,
                "metadata": {"size_bytes": file_path.stat().st_size}
            }
        except:
            content = file_path.read_text(encoding='latin-1')
            return {
                "file_name": file_path.name,
                "file_type": file_path.suffix.lstrip('.'),
                "content": content,
                "metadata": {"encoding": "latin-1"}
            }
