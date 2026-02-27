"""Approval service — can_approve, is_expired, approve, reject, apply (no LLM)."""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from apps.api.exceptions import ComioException, ForbiddenException, NotFoundException
from apps.api.models.incident import Remediation, RemediationStatus
from apps.api.models.user import User, UserRole
from apps.api.services.approval_service import (
    can_approve,
    is_expired,
    approve,
    reject,
    apply,
)


# ─── can_approve / is_expired (unit) ────────────────────────────────────────

def test_can_approve_operator():
    user = MagicMock(spec=User)
    user.role = UserRole.OPERATOR
    assert can_approve(user) is True


def test_can_approve_admin():
    user = MagicMock(spec=User)
    user.role = UserRole.ADMIN
    assert can_approve(user) is True


def test_can_approve_viewer_denied():
    user = MagicMock(spec=User)
    user.role = UserRole.VIEWER
    assert can_approve(user) is False


def test_is_expired_not_pending():
    r = MagicMock(spec=Remediation)
    r.status = RemediationStatus.APPROVED
    r.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
    assert is_expired(r) is False


def test_is_expired_recent():
    r = MagicMock(spec=Remediation)
    r.status = RemediationStatus.PENDING
    r.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    assert is_expired(r) is False


def test_is_expired_old_pending():
    r = MagicMock(spec=Remediation)
    r.status = RemediationStatus.PENDING
    r.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    assert is_expired(r) is True


# ─── approve (async) ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_raises_not_found(operator_user):
    db = MagicMock()
    rid = uuid4()
    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await approve(db, rid, operator_user, comment="ok")
    repo.get_by_id_with_incident_and_project.assert_called_once_with(db, rid)


@pytest.mark.asyncio
async def test_approve_raises_forbidden_for_viewer(viewer_user):
    db = MagicMock()
    remediation = MagicMock(spec=Remediation)
    remediation.status = RemediationStatus.PENDING
    remediation.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=remediation)
        with pytest.raises(ForbiddenException):
            await approve(db, uuid4(), viewer_user, comment="ok")


@pytest.mark.asyncio
async def test_approve_raises_when_not_pending(operator_user):
    db = MagicMock()
    remediation = MagicMock(spec=Remediation)
    remediation.status = RemediationStatus.APPROVED
    remediation.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=remediation)
        with pytest.raises(ComioException, match="already"):
            await approve(db, uuid4(), operator_user, comment="ok")


@pytest.mark.asyncio
async def test_approve_raises_when_expired(operator_user):
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    remediation = MagicMock(spec=Remediation)
    remediation.status = RemediationStatus.PENDING
    remediation.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    remediation.id = uuid4()
    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=remediation)
        with pytest.raises(ComioException, match="expired"):
            await approve(db, remediation.id, operator_user, comment="ok")
    assert remediation.status == RemediationStatus.REJECTED


@pytest.mark.asyncio
async def test_approve_success(operator_user):
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    remediation = MagicMock(spec=Remediation)
    remediation.status = RemediationStatus.PENDING
    remediation.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    remediation.id = uuid4()
    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=remediation)
        with patch("apps.api.services.approval_service._log_audit", new_callable=AsyncMock):
            out = await approve(db, remediation.id, operator_user, comment="LGTM")
    assert out is remediation
    assert remediation.status == RemediationStatus.APPROVED
    assert remediation.reviewed_by == operator_user.id
    assert remediation.review_comment == "LGTM"
    db.commit.assert_called_once()


# ─── reject (async) ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_raises_not_found(operator_user):
    db = MagicMock()
    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await reject(db, uuid4(), operator_user, reason="Nope")


@pytest.mark.asyncio
async def test_reject_raises_forbidden_for_viewer(viewer_user):
    db = MagicMock()
    remediation = MagicMock(spec=Remediation)
    remediation.status = RemediationStatus.PENDING
    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=remediation)
        with pytest.raises(ForbiddenException):
            await reject(db, uuid4(), viewer_user, reason="Nope")


@pytest.mark.asyncio
async def test_reject_success(operator_user):
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    remediation = MagicMock(spec=Remediation)
    remediation.status = RemediationStatus.PENDING
    remediation.id = uuid4()
    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=remediation)
        with patch("apps.api.services.approval_service._log_audit", new_callable=AsyncMock):
            out = await reject(db, remediation.id, operator_user, reason="Need more info")
    assert out is remediation
    assert remediation.status == RemediationStatus.REJECTED
    assert remediation.review_comment == "Need more info"
    db.commit.assert_called_once()


# ─── apply (async) ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_apply_raises_not_found(operator_user):
    db = MagicMock()
    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=None)
        with pytest.raises(NotFoundException):
            await apply(db, uuid4(), operator_user)


@pytest.mark.asyncio
async def test_apply_raises_when_not_approved(operator_user):
    db = MagicMock()
    remediation = MagicMock(spec=Remediation)
    remediation.status = RemediationStatus.PENDING
    remediation.incident = MagicMock()
    remediation.incident.project = MagicMock()
    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=remediation)
        with pytest.raises(ComioException, match="Only approved"):
            await apply(db, uuid4(), operator_user)


@pytest.mark.asyncio
async def test_apply_raises_when_no_sandbox(operator_user):
    db = MagicMock()
    remediation = MagicMock(spec=Remediation)
    remediation.status = RemediationStatus.APPROVED
    remediation.incident = MagicMock()
    remediation.incident.id = uuid4()
    remediation.incident.title = "Test"
    project = MagicMock()
    project.sandbox = None
    remediation.incident.project = project
    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=remediation)
        with pytest.raises(ComioException, match="no running sandbox"):
            await apply(db, uuid4(), operator_user)


@pytest.mark.asyncio
async def test_apply_success_with_mocked_sandbox(operator_user):
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    remediation = MagicMock(spec=Remediation)
    remediation.status = RemediationStatus.APPROVED
    remediation.id = uuid4()
    remediation.diff = "--- a/x\n+++ b/x\n"
    remediation.explanation = "Fix"
    remediation.incident = MagicMock()
    remediation.incident.id = uuid4()
    remediation.incident.title = "Incident"
    project = MagicMock()
    project.sandbox = MagicMock()
    project.sandbox.container_id = "abc123"
    remediation.incident.project = project

    with patch("apps.api.services.approval_service.remediation_repo") as repo:
        repo.get_by_id_with_incident_and_project = AsyncMock(return_value=remediation)
        with patch("apps.api.services.approval_service._log_audit", new_callable=AsyncMock):
            with patch("apps.api.services.file_ops_service.file_ops") as file_ops:
                file_ops.write_file = AsyncMock()
                file_ops.delete_file = AsyncMock()
                file_ops.create_branch = AsyncMock()
                file_ops.commit_and_push = AsyncMock()
                file_ops.create_pr = AsyncMock(side_effect=NotImplementedError())
                with patch("apps.api.services.sandbox_manager.sandbox_manager") as sm:
                    sm.exec_command = AsyncMock(return_value=MagicMock(exit_code=0))
                    out = await apply(db, remediation.id, operator_user)
    assert out is remediation
    assert remediation.status == RemediationStatus.APPLIED
    db.commit.assert_called()
