"""Text chunking for RAG — split documents into searchable chunks.

Why chunk?
- Embeddings work best on focused text (not entire documents)
- Retrieval is more precise with smaller chunks
- LLM context limits require smaller pieces

Strategy:
- Split by paragraphs/sections first
- If chunks are too large, split further by sentences
- Overlap chunks slightly to preserve context
"""

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """A chunk of text with metadata."""
    content: str           # The text content
    source: str           # Where it came from (file path, incident ID)
    content_type: str     # "runbook" | "incident" | "code" | "docs"
    metadata: dict        # Additional context (heading, line numbers, etc.)
    chunk_index: int      # Position in the source document (0, 1, 2, ...)


class TextChunker:
    """Splits documents into chunks suitable for embedding.
    
    Uses a simple but effective strategy:
    1. Split by double newlines (paragraphs)
    2. If chunks are too large, split by sentences
    3. Add small overlap between chunks
    """

    def __init__(
        self,
        chunk_size: int = 1000,      # Target characters per chunk
        chunk_overlap: int = 200,     # Overlap between chunks
        min_chunk_size: int = 100,    # Discard chunks smaller than this
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk_text(
        self,
        text: str,
        source: str,
        content_type: str,
        metadata: dict | None = None,
    ) -> list[Chunk]:
        """Split text into chunks.
        
        Args:
            text: The text to chunk
            source: Source identifier (file path, incident ID)
            content_type: Type of content
            metadata: Additional context
            
        Returns:
            List of Chunk objects
        """
        if not text or len(text) < self.min_chunk_size:
            return []

        metadata = metadata or {}
        chunks = []

        # Split by paragraphs first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        chunk_index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If adding this paragraph exceeds chunk size, save current chunk
            if current_chunk and len(current_chunk) + len(para) > self.chunk_size:
                if len(current_chunk) >= self.min_chunk_size:
                    chunks.append(
                        Chunk(
                            content=current_chunk.strip(),
                            source=source,
                            content_type=content_type,
                            metadata=metadata,
                            chunk_index=chunk_index,
                        )
                    )
                    chunk_index += 1

                # Start new chunk with overlap
                overlap_text = current_chunk[-self.chunk_overlap:] if self.chunk_overlap > 0 else ""
                current_chunk = overlap_text + " " + para if overlap_text else para
            else:
                # Add to current chunk
                current_chunk = current_chunk + "\n\n" + para if current_chunk else para

        # Don't forget the last chunk
        if current_chunk and len(current_chunk) >= self.min_chunk_size:
            chunks.append(
                Chunk(
                    content=current_chunk.strip(),
                    source=source,
                    content_type=content_type,
                    metadata=metadata,
                    chunk_index=chunk_index,
                )
            )

        return chunks

    def chunk_code(
        self,
        code: str,
        file_path: str,
        project_id: str,
    ) -> list[Chunk]:
        """Chunk code files (different strategy than prose).
        
        For code:
        - Split by functions/classes when possible
        - Keep imports with first chunk
        - Preserve structure
        
        For now, use simple chunking. TODO: Add AST-based chunking for Python.
        """
        return self.chunk_text(
            text=code,
            source=file_path,
            content_type="code",
            metadata={
                "file_path": file_path,
                "project_id": project_id,
                "language": self._detect_language(file_path),
            },
        )

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext = file_path.split(".")[-1].lower()
        language_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "jsx": "javascript",
            "tsx": "typescript",
            "go": "go",
            "rs": "rust",
            "java": "java",
            "rb": "ruby",
            "php": "php",
            "cpp": "cpp",
            "c": "c",
            "h": "c",
            "md": "markdown",
            "yaml": "yaml",
            "yml": "yaml",
            "json": "json",
        }
        return language_map.get(ext, "unknown")