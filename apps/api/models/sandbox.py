import uuid

from sqlalchemy import String, ForeignKey, Enum as SAEnum, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum

from apps.api.models.base import BaseModel


class SandboxStatus(str, Enum):
    """Current state of the sandbox container."""
    CREATING = "creating"    # Container being set up
    RUNNING = "running"      # Container is active
    STOPPED = "stopped"      # Container stopped but data preserved
    ERROR = "error"          # Something went wrong
    DESTROYING = "destroying"  # Being cleaned up


class Sandbox(BaseModel):
    __tablename__ = "sandboxes"

    container_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Docker container ID
    status: Mapped[str] = mapped_column(SAEnum(SandboxStatus), default=SandboxStatus.CREATING, nullable=False)
    git_branch: Mapped[str] = mapped_column(String(100), default="main", nullable=False)
    volume_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Docker volume name

    # Resource limits
    cpu_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)          # Number of CPU cores
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=512, nullable=False)  # Memory in MB
    disk_limit_mb: Mapped[int] = mapped_column(Integer, default=2048, nullable=False)   # Disk in MB

    # Project link — one sandbox per project
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), unique=True, nullable=False
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="sandbox")
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="sandbox")