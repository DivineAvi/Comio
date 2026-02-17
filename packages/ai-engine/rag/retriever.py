"""RAG retriever — semantic search over embeddings.

Uses pgvector for similarity search:
1. Embed the query
2. Find top-k nearest vectors (cosine similarity)
3. Return the matching chunks
"""

import logging
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.embedding import Embedding
from embeddings import EmbeddingFactory

logger = logging.getLogger(__name__)


class RAGRetriever:
    """Retrieves relevant context from the vector store."""

    def __init__(
        self,
        embedding_provider: str = "openai",
        embedding_model: str = "text-embedding-3-small",
    ):
        """Initialize retriever.
        
        Args:
            embedding_provider: Provider for embeddings
            embedding_model: Model to use for embeddings
        """
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model

    async def retrieve(
        self,
        db: AsyncSession,
        query: str,
        api_key: str,
        top_k: int = 5,
        content_types: list[str] | None = None,
        project_id: str | None = None,
    ) -> list[dict]:
        """Retrieve relevant chunks for a query.
        
        Args:
            db: Database session
            query: Search query
            api_key: API key for embedding provider
            top_k: Number of results to return
            content_types: Filter by content types (e.g., ["runbook", "incident"])
            project_id: Filter by project ID
            
        Returns:
            List of dicts with content, source, similarity, metadata
        """
        # Step 1: Embed the query
        adapter = EmbeddingFactory.create(
            provider=self.embedding_provider,
            api_key=api_key,
            model=self.embedding_model,
        )
        
        result = await adapter.embed(query)
        query_embedding = result.embedding
        
        # Step 2: Build similarity search query
        # pgvector supports multiple distance operators:
        # - <-> : L2 distance (Euclidean)
        # - <#> : inner product (dot product)
        # - <=> : cosine distance (what we use)
        
        query_sql = select(
            Embedding.id,
            Embedding.content,
            Embedding.content_type,
            Embedding.source,
            Embedding.chunk_metadata,
            Embedding.project_id,
            Embedding.incident_id,
            # Compute cosine similarity (1 - cosine_distance)
            (1 - Embedding.embedding.cosine_distance(query_embedding)).label("similarity"),
        )
        
        # Apply filters
        if content_types:
            query_sql = query_sql.where(Embedding.content_type.in_(content_types))
        
        if project_id:
            query_sql = query_sql.where(Embedding.project_id == project_id)
        
        # Order by similarity (highest first) and limit
        query_sql = query_sql.order_by(text("similarity DESC")).limit(top_k)
        
        # Step 3: Execute query
        result = await db.execute(query_sql)
        rows = result.fetchall()
        
        # Step 4: Format results
        results = []
        for row in rows:
            results.append({
                "id": str(row.id),
                "content": row.content,
                "content_type": row.content_type,
                "source": row.source,
                "metadata": row.chunk_metadata or {},
                "similarity": float(row.similarity),
                "project_id": str(row.project_id) if row.project_id else None,
                "incident_id": str(row.incident_id) if row.incident_id else None,
            })
        
        logger.info(
            "Retrieved %d chunks for query '%s...' (top_k=%d)",
            len(results),
            query[:50],
            top_k,
        )
        
        return results