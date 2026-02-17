"""Ingestion service — chunk documents and store embeddings.

This service:
1. Takes raw documents (runbooks, incident reports, code)
2. Chunks them into smaller pieces
3. Embeds each chunk
4. Stores in the embeddings table
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.embedding import Embedding
from embeddings import EmbeddingFactory
from .chunker import TextChunker, Chunk

logger = logging.getLogger(__name__)


class IngestionService:
    """Ingests documents into the RAG system."""

    def __init__(
        self,
        embedding_provider: str = "openai",
        embedding_model: str = "text-embedding-3-small",
    ):
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.chunker = TextChunker()

    async def ingest_document(
        self,
        db: AsyncSession,
        text: str,
        source: str,
        content_type: str,
        api_key: str,
        metadata: dict | None = None,
        project_id: uuid.UUID | None = None,
        incident_id: uuid.UUID | None = None,
    ) -> int:
        """Ingest a document into the RAG system.
        
        Args:
            db: Database session
            text: Document text
            source: Source identifier (file path, incident ID)
            content_type: Type ("runbook", "incident", "code", "docs")
            api_key: API key for embedding provider
            metadata: Additional context
            project_id: Optional project association
            incident_id: Optional incident association
            
        Returns:
            Number of chunks created
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for ingestion, skipping")
            return 0

        # Step 1: Chunk the text
        chunks = self.chunker.chunk_text(
            text=text,
            source=source,
            content_type=content_type,
            metadata=metadata,
        )
        
        if not chunks:
            logger.warning("No chunks generated for source: %s", source)
            return 0

        logger.info("Generated %d chunks for source: %s", len(chunks), source)

        # Step 2: Embed all chunks in batch
        adapter = EmbeddingFactory.create(
            provider=self.embedding_provider,
            api_key=api_key,
            model=self.embedding_model,
        )
        
        chunk_texts = [c.content for c in chunks]
        embedding_results = await adapter.embed_batch(chunk_texts)

        # Step 3: Create Embedding models
        embeddings = []
        for chunk, emb_result in zip(chunks, embedding_results):
            embedding = Embedding(
                content=chunk.content,
                content_type=chunk.content_type,
                source=chunk.source,
                chunk_metadata={
                    **chunk.metadata,
                    "chunk_index": chunk.chunk_index,
                    "tokens_used": emb_result.tokens_used,
                },
                embedding=emb_result.embedding,
                project_id=project_id,
                incident_id=incident_id,
            )
            embeddings.append(embedding)

        # Step 4: Bulk insert
        db.add_all(embeddings)
        await db.commit()

        logger.info(
            "Ingested %d chunks for source: %s (content_type: %s)",
            len(embeddings),
            source,
            content_type,
        )

        return len(embeddings)

    async def ingest_code_file(
        self,
        db: AsyncSession,
        file_path: str,
        code: str,
        project_id: uuid.UUID,
        api_key: str,
    ) -> int:
        """Ingest a code file from a sandbox.
        
        Args:
            db: Database session
            file_path: Path to the file in the sandbox
            code: File contents
            project_id: Project this code belongs to
            api_key: API key for embedding provider
            
        Returns:
            Number of chunks created
        """
        chunks = self.chunker.chunk_code(
            code=code,
            file_path=file_path,
            project_id=str(project_id),
        )

        if not chunks:
            return 0

        # Embed and store
        adapter = EmbeddingFactory.create(
            provider=self.embedding_provider,
            api_key=api_key,
            model=self.embedding_model,
        )

        chunk_texts = [c.content for c in chunks]
        embedding_results = await adapter.embed_batch(chunk_texts)

        embeddings = []
        for chunk, emb_result in zip(chunks, embedding_results):
            embedding = Embedding(
                content=chunk.content,
                content_type="code",
                source=chunk.source,
                chunk_metadata={
                    **chunk.metadata,
                    "chunk_index": chunk.chunk_index,
                    "tokens_used": emb_result.tokens_used,
                },
                embedding=emb_result.embedding,
                project_id=project_id,
            )
            embeddings.append(embedding)

        db.add_all(embeddings)
        await db.commit()

        logger.info(
            "Ingested code file: %s (%d chunks, project: %s)",
            file_path,
            len(embeddings),
            project_id,
        )

        return len(embeddings)