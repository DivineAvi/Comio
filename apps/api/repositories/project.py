"""Project repository with project-specific database operations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.project import Project
from apps.api.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def __init__(self):
        super().__init__(Project)

    async def get_by_owner(
        self, db: AsyncSession, owner_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> list[Project]:
        """Get all projects owned by a specific user."""
        result = await db.execute(
            select(Project)
            .where(Project.owner_id == owner_id)
            .offset(skip)
            .limit(limit)
            .order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_with_sandbox(self, db: AsyncSession, project_id: uuid.UUID) -> Project | None:
        """Get a project with its sandbox eagerly loaded.

        Without 'selectinload', accessing project.sandbox would trigger
        a separate database query (lazy loading). With it, both are
        fetched in one query — more efficient.
        """
        result = await db.execute(
            select(Project)
            .where(Project.id == project_id)
            .options(selectinload(Project.sandbox))
        )
        return result.scalar_one_or_none()

    async def count_by_owner(self, db: AsyncSession, owner_id: uuid.UUID) -> int:
        """Count projects owned by a user."""
        from sqlalchemy import func
        result = await db.execute(
            select(func.count()).select_from(Project).where(Project.owner_id == owner_id)
        )
        return result.scalar_one()


# Singleton instance
project_repo = ProjectRepository()