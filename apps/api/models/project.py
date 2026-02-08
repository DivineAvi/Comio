import uuid

from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum

from apps.api.models.base import BaseModel


class ProjectOrigin(str, Enum):
    """How the project was created."""
    CLONED = "cloned"      # Imported from an existing GitHub repo
    CREATED = "created"    # Built from scratch by AI in Comio


class ProjectType(str, Enum):
    """What kind of project this is."""
    API = "api"
    WEB = "web"
    FULLSTACK = "fullstack"
    CLI = "cli"
    LIBRARY = "library"
    OTHER = "other"


class Project(BaseModel):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(SAEnum(ProjectOrigin), nullable=False)
    project_type: Mapped[str] = mapped_column(SAEnum(ProjectType), default=ProjectType.OTHER, nullable=False)

    # GitHub repo info — null for newly created projects until published
    repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    repo_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. "user/repo"
    default_branch: Mapped[str] = mapped_column(String(100), default="main", nullable=False)

    # Monitoring config — what metrics to watch (stored as JSON)
    monitoring_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Owner
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Relationships
    owner: Mapped["User"] = relationship(back_populates="projects")
    sandbox: Mapped["Sandbox | None"] = relationship(back_populates="project", uselist=False)  # One sandbox per project
    incidents: Mapped[list["Incident"]] = relationship(back_populates="project")
    deployments: Mapped[list["Deployment"]] = relationship(back_populates="project")