"""Seed runbooks into the RAG system.

This script:
1. Reads runbook markdown files from docs/runbooks/
2. Chunks them
3. Embeds them
4. Stores in the embeddings table

Run: python scripts/seed_runbooks.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path so we can import our modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from apps.api.config import settings
from rag import IngestionService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)


async def seed_runbooks():
    """Seed runbooks from docs/runbooks/ directory."""
    
    # Create database connection
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Initialize ingestion service
    ingestion = IngestionService(
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    
    # Check API key
    if not settings.openai_api_key:
        logger.error("OPENAI_API_KEY not set in .env file")
        return
    
    # Find all runbook files
    runbooks_dir = project_root / "docs" / "runbooks"
    if not runbooks_dir.exists():
        logger.error("Runbooks directory not found: %s", runbooks_dir)
        return
    
    runbook_files = list(runbooks_dir.glob("*.md"))
    if not runbook_files:
        logger.warning("No runbook files found in %s", runbooks_dir)
        return
    
    logger.info("Found %d runbook files to ingest", len(runbook_files))
    
    # Ingest each runbook
    total_chunks = 0
    
    async with async_session() as db:
        for runbook_file in runbook_files:
            logger.info("Ingesting: %s", runbook_file.name)
            
            # Read file content
            with open(runbook_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Ingest into RAG system
            num_chunks = await ingestion.ingest_document(
                db=db,
                text=content,
                source=f"runbooks/{runbook_file.name}",
                content_type="runbook",
                api_key=settings.openai_api_key,
                metadata={
                    "filename": runbook_file.name,
                    "title": runbook_file.stem.replace("-", " ").title(),
                },
                project_id=None,  # Runbooks are global, not project-specific
                incident_id=None,
            )
            
            total_chunks += num_chunks
            logger.info("✅ %s → %d chunks", runbook_file.name, num_chunks)
    
    await engine.dispose()
    
    logger.info("✅ Seeding complete! Total chunks created: %d", total_chunks)


if __name__ == "__main__":
    asyncio.run(seed_runbooks())