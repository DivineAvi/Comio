import uuid

from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum

from apps.api.models.base import BaseModel


class DeploymentStatus(str, Enum):
    BUILDING = "building"
    DEPLOYING = "deploying"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"


class Deployment(BaseModel):
    __tablename__ = "deployments"

    status: Mapped[str] = mapped_column(SAEnum(DeploymentStatus), default=DeploymentStatus.BUILDING, nullable=False)
    environment: Mapped[str] = mapped_column(String(50), default="staging", nullable=False)  # staging, production
    deploy_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # e.g. https://my-app.comio.dev
    image_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Docker image tag
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)  # Git commit deployed

    # Build and deploy logs
    build_logs: Mapped[str | None] = mapped_column(Text, nullable=True)
    deploy_logs: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Resource usage snapshot
    resource_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Project link
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    # Who triggered it
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="deployments")
    trigger_user: Mapped["User | None"] = relationship()
