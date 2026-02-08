"""Deployment schemas for request validation and response serialization."""

import uuid

from pydantic import BaseModel, Field

from apps.api.schemas.base import BaseResponse


# ── Request Schemas ────────────────────────────────────

class DeployRequest(BaseModel):
    """Data to trigger a deployment."""
    environment: str = Field(default="staging", description="staging or production")


class DeployStopRequest(BaseModel):
    """Data to stop a running deployment."""
    reason: str | None = None


# ── Response Schemas ───────────────────────────────────

class DeploymentResponse(BaseResponse):
    """Deployment data returned by the API."""
    status: str
    environment: str
    deploy_url: str | None = None
    image_tag: str | None = None
    commit_sha: str | None = None
    project_id: uuid.UUID
    triggered_by: uuid.UUID | None = None


class DeploymentDetailResponse(DeploymentResponse):
    """Deployment with logs included (for detail view)."""
    build_logs: str | None = None
    deploy_logs: str | None = None
    resource_usage: dict | None = None


class DeploymentListResponse(BaseModel):
    """List of deployments for a project."""
    deployments: list[DeploymentResponse]
    total: int