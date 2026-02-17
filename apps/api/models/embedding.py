"""Embedding model — stores text chunks and their vector embeddings."""

import uuid
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from apps.api.models.base import BaseModel


class Embedding(BaseModel):
    """Vector embeddings for semantic search.
    
    Stores text chunks (from runbooks, incidents, code, docs) along with
    their vector representations for similarity search.
    """
    __tablename__ = "embeddings"

    # Content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "runbook" | "incident" | "code" | "docs"
    source: Mapped[str] = mapped_column(String(500), nullable=False)  # File path or incident ID
    chunk_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)  # Additional context
    
    # Vector embedding (1536 dimensions for OpenAI text-embedding-3-small)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    
    # Optional foreign keys
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("projects.id", ondelete="CASCADE"), 
        nullable=True
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("incidents.id", ondelete="CASCADE"), 
        nullable=True
    )
    
    # Relationships
    project: Mapped["Project | None"] = relationship("Project", back_populates="embeddings")
    incident: Mapped["Incident | None"] = relationship("Incident", back_populates="embeddings")