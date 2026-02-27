"""Remediation routes — list pending, approve, reject, apply."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import get_current_user, require_operator_or_admin
from apps.api.database import get_db
from apps.api.models.user import User
from apps.api.repositories.remediation import remediation_repo
from apps.api.schemas.incident import RemediationResponse, RemediationApprove, RemediationReject
from apps.api.services.approval_service import approve, reject, apply

router = APIRouter(prefix="/remediations", tags=["remediations"])


def _remediation_to_response(r):
    return RemediationResponse(
        id=r.id,
        created_at=r.created_at,
        updated_at=r.updated_at,
        fix_type=r.fix_type,
        diff=r.diff,
        files_changed=r.files_changed,
        explanation=r.explanation,
        risk_level=r.risk_level,
        status=r.status,
        pr_url=r.pr_url,
        pr_number=r.pr_number,
        reviewed_by=r.reviewed_by,
        review_comment=r.review_comment,
    )


@router.get("", response_model=list[RemediationResponse])
async def list_remediations(
    status: str = Query(default="pending", description="Filter by status (e.g. pending)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_expired: bool = Query(default=False, description="Include pending remediations older than 24h"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List remediations for projects you own. Default: pending, excluding expired (24h)."""
    from apps.api.models.incident import RemediationStatus
    if status != RemediationStatus.PENDING.value:
        return []  # Only pending list is implemented here; extend as needed
    items = await remediation_repo.list_pending_for_user(
        db, current_user.id, skip=skip, limit=limit, include_expired=include_expired
    )
    return [_remediation_to_response(r) for r in items]


@router.post("/{remediation_id}/approve", response_model=RemediationResponse)
async def approve_remediation(
    remediation_id: uuid.UUID,
    body: RemediationApprove,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending remediation (operator/admin only). 24h expiry."""
    r = await approve(db, remediation_id, current_user, comment=body.comment)
    return _remediation_to_response(r)


@router.post("/{remediation_id}/reject", response_model=RemediationResponse)
async def reject_remediation(
    remediation_id: uuid.UUID,
    body: RemediationReject,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending remediation with a reason (operator/admin only)."""
    r = await reject(db, remediation_id, current_user, reason=body.reason)
    return _remediation_to_response(r)


@router.post("/{remediation_id}/apply", response_model=RemediationResponse)
async def apply_remediation(
    remediation_id: uuid.UUID,
    current_user: User = Depends(require_operator_or_admin),
    db: AsyncSession = Depends(get_db),
):
    """Apply an approved fix in the project sandbox (commit, push, create PR). Operator/admin only."""
    r = await apply(db, remediation_id, current_user)
    return _remediation_to_response(r)