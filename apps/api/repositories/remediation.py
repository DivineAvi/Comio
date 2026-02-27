"""Remediation repository — list pending, get by id with incident and project."""

import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.incident import Incident, Remediation, RemediationStatus
from apps.api.models.project import Project
from apps.api.repositories.base import BaseRepository


class RemediationRepository(BaseRepository[Remediation]):
    def __init__(self):
        super().__init__(Remediation)

    async def get_by_id_with_incident_and_project(
        self, db: AsyncSession, remediation_id: uuid.UUID
    ) -> Remediation | None:
        """Load remediation with incident, project, and sandbox (for apply and ownership checks)."""
        result = await db.execute(
            select(Remediation)
            .where(Remediation.id == remediation_id)
            .options(
                selectinload(Remediation.incident).selectinload(Incident.project).selectinload(Project.sandbox),
            )
        )
        return result.scalar_one_or_none()

    async def list_pending_for_user(
        self,
        db: AsyncSession,
        owner_id: uuid.UUID,
        *,
        skip: int = 0,
        limit: int = 50,
        include_expired: bool = False,
    ) -> list[Remediation]:
        """List remediations with status=pending for projects owned by owner_id.
        Optionally exclude remediations older than 24h (expired).
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)) if not include_expired else None
        q = (
            select(Remediation)
            .join(Incident, Remediation.incident_id == Incident.id)
            .join(Project, Incident.project_id == Project.id)
            .where(Project.owner_id == owner_id)
            .where(Remediation.status == RemediationStatus.PENDING)
        )
        if cutoff is not None:
            q = q.where(Remediation.created_at >= cutoff)
        q = q.order_by(Remediation.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(q.options(selectinload(Remediation.incident).selectinload(Incident.project)))
        return list(result.scalars().unique().all())


remediation_repo = RemediationRepository()