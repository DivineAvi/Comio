"""Incident routes — list, get details, approve/reject remediations.

Incidents are created automatically by the anomaly detector (Day 15+)
or manually via the API. These routes let users manage them.

All routes are protected — require a valid JWT token.
Users can only see incidents for projects they own.
"""

import logging
import uuid

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import get_current_user
from apps.api.database import get_db
from apps.api.exceptions import NotFoundException, ForbiddenException, ComioException
from apps.api.models.incident import Incident, IncidentStatus
from apps.api.models.user import User
from apps.api.repositories import project_repo
from apps.api.repositories.incident import incident_repo
from apps.api.services.rca_service import rca_service
from apps.api.services.approval_service import approve as approval_approve, reject as approval_reject
from apps.api.schemas.incident import (
    IncidentCreate,
    IncidentResponse,
    IncidentListResponse,
    DiagnosisResponse,
    RemediationResponse,
    RemediationApprove,
    RemediationReject,
    GenerateFixRequest,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])


# ── Helpers ───────────────────────────────────────────

def _diagnosis_to_response(diagnosis) -> DiagnosisResponse | None:
    """Convert a Diagnosis model to its response schema."""
    if not diagnosis:
        return None
    return DiagnosisResponse(
        id=diagnosis.id,
        created_at=diagnosis.created_at,
        updated_at=diagnosis.updated_at,
        root_cause=diagnosis.root_cause,
        category=diagnosis.category,
        confidence=diagnosis.confidence,
        explanation=diagnosis.explanation,
        evidence=diagnosis.evidence,
        affected_components=diagnosis.affected_components,
        suggested_actions=diagnosis.suggested_actions,
        llm_provider=diagnosis.llm_provider,
        llm_model=diagnosis.llm_model,
    )


def _remediation_to_response(remediation) -> RemediationResponse | None:
    """Convert a Remediation model to its response schema."""
    if not remediation:
        return None
    return RemediationResponse(
        id=remediation.id,
        created_at=remediation.created_at,
        updated_at=remediation.updated_at,
        fix_type=remediation.fix_type,
        diff=remediation.diff,
        files_changed=remediation.files_changed,
        explanation=remediation.explanation,
        risk_level=remediation.risk_level,
        status=remediation.status,
        pr_url=remediation.pr_url,
        pr_number=remediation.pr_number,
        reviewed_by=remediation.reviewed_by,
        review_comment=remediation.review_comment,
    )


def _incident_to_response(incident: Incident, include_relations: bool = False) -> IncidentResponse:
    """Convert an Incident model to its response schema.

    Args:
        include_relations: If True, include diagnosis and remediation.
            Only set this when the incident was loaded with selectinload
            (e.g. via get_with_details). For freshly created incidents
            or list queries, set to False to avoid lazy loading errors.
    """
    diagnosis = None
    remediation = None

    if include_relations:
        # Safe to access — these were eagerly loaded
        diagnosis = _diagnosis_to_response(incident.diagnosis)
        remediation = _remediation_to_response(incident.remediation)

    return IncidentResponse(
        id=incident.id,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        title=incident.title,
        description=incident.description,
        severity=incident.severity,
        status=incident.status,
        source=incident.source,
        project_id=incident.project_id,
        diagnosis=diagnosis,
        remediation=remediation,
    )


async def _verify_project_ownership(
    project_id: uuid.UUID, current_user: User, db: AsyncSession
) -> None:
    """Verify the user owns the project this incident belongs to."""
    project = await project_repo.get_by_id(db, project_id)
    if not project:
        raise NotFoundException("Project", str(project_id))
    if project.owner_id != current_user.id:
        raise ForbiddenException("You don't have access to this project's incidents")


# ── Routes ────────────────────────────────────────────

@router.post("", response_model=IncidentResponse, status_code=201)
async def create_incident(
    body: IncidentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually create an incident for a project.

    Most incidents will be auto-created by the anomaly detector (Day 15+),
    but this endpoint allows manual incident creation for testing or
    when users spot issues themselves.
    """
    await _verify_project_ownership(body.project_id, current_user, db)

    incident = await incident_repo.create(
        db,
        title=body.title,
        description=body.description,
        severity=body.severity,
        source=body.source,
        project_id=body.project_id,
    )

    return _incident_to_response(incident)


@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    project_id: uuid.UUID = Query(description="Filter incidents by project ID"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List incidents for a project, newest first.

    Requires project_id as a query parameter:
        GET /incidents?project_id=<uuid>
    """
    await _verify_project_ownership(project_id, current_user, db)

    incidents = await incident_repo.get_by_project(db, project_id, skip=skip, limit=limit)
    total = await incident_repo.count_by_project(db, project_id)

    return IncidentListResponse(
        incidents=[_incident_to_response(i) for i in incidents],
        total=total,
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get incident details including diagnosis and remediation (if available)."""
    incident = await incident_repo.get_with_details(db, incident_id)
    if not incident:
        raise NotFoundException("Incident", str(incident_id))

    await _verify_project_ownership(incident.project_id, current_user, db)

    return _incident_to_response(incident, include_relations=True)


@router.get("/{incident_id}/diagnosis", response_model=DiagnosisResponse)
async def get_diagnosis(
    incident_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the diagnosis for an incident.
    
    Returns the AI-generated root cause analysis, affected components,
    and suggested actions.
    """
    incident = await incident_repo.get_with_details(db, incident_id)
    if not incident:
        raise NotFoundException("Incident", str(incident_id))

    await _verify_project_ownership(incident.project_id, current_user, db)

    if not incident.diagnosis:
        raise NotFoundException("Diagnosis", "No diagnosis available for this incident")

    return _diagnosis_to_response(incident.diagnosis)


@router.post("/{incident_id}/diagnose", response_model=IncidentResponse)
async def trigger_diagnosis(
    incident_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger RCA diagnosis for an incident.
    
    Useful for:
    - Retrying failed diagnoses
    - Re-analyzing after gathering more context
    - Manual diagnosis of older incidents
    
    Note: This will replace any existing diagnosis.
    """
    incident = await incident_repo.get_with_details(db, incident_id)
    if not incident:
        raise NotFoundException("Incident", str(incident_id))

    await _verify_project_ownership(incident.project_id, current_user, db)

    # If diagnosis exists, delete it first
    if incident.diagnosis:
        await db.delete(incident.diagnosis)
        await db.commit()
        await db.refresh(incident)

    # Run RCA
    logger = logging.getLogger(__name__)
    logger.info("Manual diagnosis triggered for incident %s by user %s", incident_id, current_user.id)
    
    diagnosis_result = await rca_service.rca_engine.diagnose(db, incident)

    # Create database Diagnosis model
    from apps.api.models.incident import Diagnosis as DiagnosisModel
    from apps.api.config import settings
    
    diagnosis_model = DiagnosisModel(
        incident_id=incident.id,
        root_cause=diagnosis_result.root_cause,
        category=diagnosis_result.category.value,
        confidence=diagnosis_result.confidence,
        explanation=diagnosis_result.reasoning,
        evidence=[e.__dict__ for e in diagnosis_result.evidence],
        affected_components=diagnosis_result.affected_components,
        suggested_actions=[a.__dict__ for a in diagnosis_result.suggested_actions],
        llm_provider=settings.default_llm_provider,
        llm_model=settings.default_llm_model,
    )
    
    db.add(diagnosis_model)
    incident.status = IncidentStatus.DIAGNOSED
    await db.commit()
    await db.refresh(incident)

    return _incident_to_response(incident, include_relations=True)


@router.post("/{incident_id}/generate-fix", response_model=IncidentResponse)
async def generate_fix(
    incident_id: uuid.UUID,
    body: GenerateFixRequest = Body(default_factory=GenerateFixRequest),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a fix proposal from the incident's diagnosis (Day 13).

    Requires the incident to have a diagnosis first (run diagnose if needed).
    Optionally pass code_context (file path -> content) from the project sandbox
    so the LLM can propose concrete code changes.
    """
    incident = await incident_repo.get_with_details(db, incident_id)
    if not incident:
        raise NotFoundException("Incident", str(incident_id))

    await _verify_project_ownership(incident.project_id, current_user, db)

    try:
        from apps.api.services.fix_service import generate_fix_for_incident

        await generate_fix_for_incident(db, incident_id, code_context=body.code_context or None)
        await db.commit()
    except ValueError as e:
        raise ComioException(str(e), status_code=400)

    await db.refresh(incident)
    incident = await incident_repo.get_with_details(db, incident_id)
    return _incident_to_response(incident, include_relations=True)


@router.post("/{incident_id}/approve", response_model=IncidentResponse)
async def approve_remediation(
    incident_id: uuid.UUID,
    body: RemediationApprove,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a proposed remediation (fix) for an incident.

    After approval, use POST /remediations/{id}/apply to create the PR.
    Only operators and admins can approve. Pending remediations expire after 24h.
    """
    incident = await incident_repo.get_with_details(db, incident_id)
    if not incident:
        raise NotFoundException("Incident", str(incident_id))

    await _verify_project_ownership(incident.project_id, current_user, db)

    if not incident.remediation:
        raise ComioException("No remediation proposed for this incident", status_code=400)

    await approval_approve(db, incident.remediation.id, current_user, comment=body.comment)
    incident = await incident_repo.get_with_details(db, incident_id)
    return _incident_to_response(incident, include_relations=True)


@router.post("/{incident_id}/reject", response_model=IncidentResponse)
async def reject_remediation(
    incident_id: uuid.UUID,
    body: RemediationReject,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a proposed remediation with a reason. Only operators and admins can reject."""
    incident = await incident_repo.get_with_details(db, incident_id)
    if not incident:
        raise NotFoundException("Incident", str(incident_id))

    await _verify_project_ownership(incident.project_id, current_user, db)

    if not incident.remediation:
        raise ComioException("No remediation proposed for this incident", status_code=400)

    await approval_reject(db, incident.remediation.id, current_user, reason=body.reason)
    incident = await incident_repo.get_with_details(db, incident_id)
    return _incident_to_response(incident, include_relations=True)