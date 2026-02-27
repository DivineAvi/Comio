"""Human-in-the-loop approval: approve, reject, apply remediations.
Role-based (operator/admin), 24h expiry, audit log, apply via sandbox + PR.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.exceptions import ComioException, ForbiddenException, NotFoundException
from apps.api.models.incident import Incident, Remediation, RemediationStatus
from apps.api.models.user import User, UserRole
from apps.api.repositories.remediation import remediation_repo
from apps.api.repositories.incident import incident_repo

logger = logging.getLogger(__name__)

# 24h after creation, pending remediations are considered expired
PENDING_EXPIRY_HOURS = 24


def can_approve(user: User) -> bool:
    """Only operator or admin can approve/reject/apply."""
    return user.role in (UserRole.OPERATOR, UserRole.ADMIN)


def is_expired(remediation: Remediation) -> bool:
    """True if still pending and created more than PENDING_EXPIRY_HOURS ago."""
    if remediation.status != RemediationStatus.PENDING:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=PENDING_EXPIRY_HOURS)
    return remediation.created_at < cutoff


async def _log_audit(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: str,
    user_id: uuid.UUID | None,
    details: dict | None = None,
) -> None:
    from apps.api.models.audit_log import AuditLog
    db.add(AuditLog(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        details=details,
    ))


async def approve(
    db: AsyncSession,
    remediation_id: uuid.UUID,
    user: User,
    comment: str | None = None,
) -> Remediation:
    """Approve a pending remediation. Caller must commit."""
    remediation = await remediation_repo.get_by_id_with_incident_and_project(db, remediation_id)
    if not remediation:
        raise NotFoundException("Remediation", str(remediation_id))
    if not can_approve(user):
        raise ForbiddenException("Only operators or admins can approve remediations")
    if remediation.status != RemediationStatus.PENDING:
        raise ComioException(f"Remediation is already {remediation.status}", status_code=400)
    if is_expired(remediation):
        remediation.status = RemediationStatus.REJECTED
        remediation.reviewed_by = None
        remediation.review_comment = "Auto-rejected: approval window expired (24h)"
        await _log_audit(db, "remediation.expired", "remediation", str(remediation_id), user.id, {"reason": "24h expiry"})
        await db.commit()
        await db.refresh(remediation)
        raise ComioException("This remediation has expired (24h). It was auto-rejected.", status_code=400)

    remediation.status = RemediationStatus.APPROVED
    remediation.reviewed_by = user.id
    remediation.review_comment = comment
    await _log_audit(db, "remediation.approved", "remediation", str(remediation_id), user.id, {"comment": comment})
    await db.commit()
    await db.refresh(remediation)
    return remediation


async def reject(
    db: AsyncSession,
    remediation_id: uuid.UUID,
    user: User,
    reason: str,
) -> Remediation:
    """Reject a pending remediation. Caller must commit."""
    remediation = await remediation_repo.get_by_id_with_incident_and_project(db, remediation_id)
    if not remediation:
        raise NotFoundException("Remediation", str(remediation_id))
    if not can_approve(user):
        raise ForbiddenException("Only operators or admins can reject remediations")
    if remediation.status != RemediationStatus.PENDING:
        raise ComioException(f"Remediation is already {remediation.status}", status_code=400)

    remediation.status = RemediationStatus.REJECTED
    remediation.reviewed_by = user.id
    remediation.review_comment = reason
    await _log_audit(db, "remediation.rejected", "remediation", str(remediation_id), user.id, {"reason": reason})
    await db.commit()
    await db.refresh(remediation)
    return remediation


async def apply(
    db: AsyncSession,
    remediation_id: uuid.UUID,
    user: User,
) -> Remediation:
    """Execute an approved fix: apply diff in sandbox, commit, push, create PR. Caller must commit after."""
    remediation = await remediation_repo.get_by_id_with_incident_and_project(db, remediation_id)
    if not remediation:
        raise NotFoundException("Remediation", str(remediation_id))
    if not can_approve(user):
        raise ForbiddenException("Only operators or admins can apply remediations")
    if remediation.status != RemediationStatus.APPROVED:
        raise ComioException("Only approved remediations can be applied", status_code=400)

    incident = remediation.incident
    project = incident.project
    if not project.sandbox or not project.sandbox.container_id:
        raise ComioException("Project has no running sandbox; cannot apply fix", status_code=400)

    from apps.api.services.file_ops_service import file_ops
    from apps.api.services.sandbox_manager import sandbox_manager

    container_id = project.sandbox.container_id
    patch_content = remediation.diff

    # 1) Write patch file in sandbox
    patch_path = "/workspace/.comio_fix.patch"
    await file_ops.write_file(container_id, patch_path, patch_content)

    # 2) Apply patch
    result = await sandbox_manager.exec_command(container_id, ["patch", "-p1", "--forward", "-i", patch_path], timeout=60)
    await file_ops.delete_file(container_id, patch_path)

    if result.exit_code != 0:
        remediation.status = RemediationStatus.FAILED
        await _log_audit(db, "remediation.apply_failed", "remediation", str(remediation_id), user.id, {"stderr": result.stderr})
        await db.commit()
        await db.refresh(remediation)
        raise ComioException(f"Failed to apply patch: {result.stderr or result.stdout}", status_code=500)

    # 3) Commit and push (branch created by caller or use a default)
    branch_name = f"fix/incident-{incident.id}"
    try:
        await file_ops.create_branch(container_id, branch_name)
    except Exception:
        pass  # branch may already exist
    await file_ops.commit_and_push(container_id, f"Apply fix for incident {incident.id}")
    pr_url = None
    pr_number = None
    try:
        pr_url = await file_ops.create_pr(container_id, f"Fix: {incident.title}", remediation.explanation[:500], base="main")
        if pr_url and "/pull/" in pr_url:
            pr_number = int(pr_url.rstrip("/").split("/pull/")[-1])
    except NotImplementedError:
        logger.warning("create_pr not implemented; PR not created")
    except Exception as e:
        logger.warning("create_pr failed: %s", e)

    remediation.status = RemediationStatus.APPLIED
    remediation.pr_url = pr_url
    remediation.pr_number = pr_number
    await _log_audit(db, "remediation.applied", "remediation", str(remediation_id), user.id, {"pr_url": pr_url})
    await db.commit()
    await db.refresh(remediation)
    return remediation