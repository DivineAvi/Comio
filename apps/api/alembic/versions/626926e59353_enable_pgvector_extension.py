"""enable pgvector extension

Revision ID: 626926e59353
Revises: 26d1728a5de0
Create Date: 2026-02-17 14:49:55.689679

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = '626926e59353'
down_revision: Union[str, Sequence[str], None] = '26d1728a5de0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - enable pgvector and create embeddings table."""
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    # Create embeddings table
    op.create_table(
        "embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        
        # Content metadata
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),  # "runbook" | "incident" | "code" | "docs"
        sa.Column("source", sa.String(500), nullable=False),  # File path or incident ID
        sa.Column("metadata", JSONB, nullable=True),  # Additional context
        
        # Embedding vector (1536 dimensions for OpenAI text-embedding-3-small)
        # Using pgvector's 'vector' type
        sa.Column("embedding", sa.Text, nullable=False),  # Will be cast to vector(1536) via raw SQL
        
        # Optional foreign keys
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("incident_id", UUID(as_uuid=True), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True),
    )
    
    # Manually set the embedding column to vector type (Alembic doesn't support it directly)
    op.execute("ALTER TABLE embeddings ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536)")
    
    # Create indexes for efficient similarity search
    op.create_index(
        "ix_embeddings_content_type",
        "embeddings",
        ["content_type"]
    )
    op.create_index(
        "ix_embeddings_project_id",
        "embeddings",
        ["project_id"]
    )
    
    # Create HNSW index for fast approximate nearest neighbor search
    # HNSW (Hierarchical Navigable Small World) is faster than IVFFlat for most use cases
    op.execute(
        "CREATE INDEX embeddings_embedding_idx ON embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """Downgrade schema - remove embeddings table and pgvector extension."""
    op.drop_index("embeddings_embedding_idx", table_name="embeddings")
    op.drop_index("ix_embeddings_project_id", table_name="embeddings")
    op.drop_index("ix_embeddings_content_type", table_name="embeddings")
    op.drop_table("embeddings")
    op.execute("DROP EXTENSION IF EXISTS vector")
