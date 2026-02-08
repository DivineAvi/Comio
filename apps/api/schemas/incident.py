"""Incident schemas for request validation and response serialization."""

import uuid

from pydantic import BaseModel, Field

from apps.api.schemas.base import BaseResponse


# ── Request Schemas ────────────────────────────────────

class IncidentCreate(BaseModel):
    """Data to manually create an incident (most are auto-created by the anomaly detector)."""
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    severity: str = Field(default="medium", description="critical, high, medium, low, info")
    source: str = Field(default="manual")
    project_id: uuid.UUID


class RemediationApprove(BaseModel):
    """Data to approve a proposed fix."""
    comment: str | None = None


class RemediationReject(BaseModel):
    """Data to reject a proposed fix."""
    reason: str = Field(min_length=1)


# ── Response Schemas ───────────────────────────────────

class DiagnosisResponse(BaseResponse):
    """AI diagnosis of an incident."""
    root_cause: str
    category: str
    confidence: float
    explanation: str
    evidence: dict | None = None
    affected_components: list | None = None
    suggested_actions: list | None = None
    llm_provider: str | None = None
    llm_model: str | None = None


class RemediationResponse(BaseResponse):
    """Proposed fix for an incident."""
    fix_type: str
    diff: str
    files_changed: list | None = None
    explanation: str
    risk_level: str
    status: str
    pr_url: str | None = None
    pr_number: int | None = None
    reviewed_by: uuid.UUID | None = None
    review_comment: str | None = None


class IncidentResponse(BaseResponse):
    """Incident data returned by the API."""
    title: str
    description: str | None = None
    severity: str
    status: str
    source: str
    project_id: uuid.UUID
    diagnosis: DiagnosisResponse | None = None
    remediation: RemediationResponse | None = None


class IncidentListResponse(BaseModel):
    """Paginated list of incidents."""
    incidents: list[IncidentResponse]
    total: int