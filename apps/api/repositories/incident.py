"""Incident repository with incident-specific database operations."""

import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.incident import Incident, Remediation
from apps.api.repositories.base import BaseRepository


class IncidentRepository(BaseRepository[Incident]):
    def __init__(self):
        super().__init__(Incident)

    async def get_by_project(
        self, db: AsyncSession, project_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> list[Incident]:
        """Get all incidents for a specific project, newest first."""
        result = await db.execute(
            select(Incident)
            .where(Incident.project_id == project_id)
            .offset(skip)
            .limit(limit)
            .order_by(Incident.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_with_details(self, db: AsyncSession, incident_id: uuid.UUID) -> Incident | None:
        """Get an incident with its diagnosis and remediation eagerly loaded.

        Without selectinload, accessing incident.diagnosis would trigger
        a separate database query. This loads everything in one go.
        """
        result = await db.execute(
            select(Incident)
            .where(Incident.id == incident_id)
            .options(
                selectinload(Incident.diagnosis),
                selectinload(Incident.remediation),
            )
        )
        return result.scalar_one_or_none()

    async def count_by_project(self, db: AsyncSession, project_id: uuid.UUID) -> int:
        """Count incidents for a specific project."""
        result = await db.execute(
            select(func.count()).select_from(Incident).where(Incident.project_id == project_id)
        )
        return result.scalar_one()


# Singleton instance
incident_repo = IncidentRepository()