"""Sandbox repository with sandbox-specific database operations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.sandbox import Sandbox, SandboxStatus
from apps.api.repositories.base import BaseRepository


class SandboxRepository(BaseRepository[Sandbox]):
    def __init__(self):
        super().__init__(Sandbox)

    async def get_by_project(self, db: AsyncSession, project_id: uuid.UUID) -> Sandbox | None:
        """Get the sandbox for a specific project.

        Each project has at most one sandbox (one-to-one relationship).
        """
        result = await db.execute(
            select(Sandbox).where(Sandbox.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, db: AsyncSession, sandbox: Sandbox, status: SandboxStatus
    ) -> Sandbox:
        """Update a sandbox's status."""
        sandbox.status = status
        await db.commit()
        await db.refresh(sandbox)
        return sandbox


# Singleton instance
sandbox_repo = SandboxRepository()