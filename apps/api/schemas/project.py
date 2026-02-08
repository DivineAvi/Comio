"""Project schemas for request validation and response serialization."""

import uuid

from pydantic import BaseModel, Field

from apps.api.schemas.base import BaseResponse


# ── Request Schemas ────────────────────────────────────

class ProjectImport(BaseModel):
    """Data to import an existing GitHub repository as a project."""
    repo_url: str = Field(description="GitHub repository URL, e.g. https://github.com/user/repo")
    name: str | None = None                   # If not provided, derived from repo name
    description: str | None = None


class ProjectCreate(BaseModel):
    """Data to create a brand new project from scratch (AI builds it)."""
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, description="Describe what you want the AI to build")
    project_type: str = Field(default="other", description="api, web, fullstack, cli, library, other")


class ProjectUpdate(BaseModel):
    """Fields that can be updated on a project. All optional."""
    name: str | None = None
    description: str | None = None
    monitoring_config: dict | None = None


# ── Response Schemas ───────────────────────────────────

class ProjectResponse(BaseResponse):
    """Project data returned by the API."""
    name: str
    description: str | None = None
    origin: str                          # "cloned" or "created"
    project_type: str
    repo_url: str | None = None
    repo_full_name: str | None = None
    default_branch: str
    owner_id: uuid.UUID
    monitoring_config: dict | None = None


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""
    projects: list[ProjectResponse]
    total: int
