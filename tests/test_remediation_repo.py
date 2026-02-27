"""Remediation repository — list_pending_for_user, get_by_id_with_incident_and_project."""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.incident import Remediation, RemediationStatus
from apps.api.repositories.remediation import remediation_repo


@pytest.mark.asyncio
async def test_list_pending_for_user_returns_empty_when_none():
    db = MagicMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalars.return_value.unique.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result_mock)
    owner_id = uuid4()
    items = await remediation_repo.list_pending_for_user(db, owner_id, skip=0, limit=20, include_expired=False)
    assert items == []
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_by_id_with_incident_and_project_returns_none_when_not_found():
    db = MagicMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=result_mock)
    out = await remediation_repo.get_by_id_with_incident_and_project(db, uuid4())
    assert out is None
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_by_id_returns_remediation_when_found():
    remediation = MagicMock(spec=Remediation)
    remediation.id = uuid4()
    db = MagicMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=remediation)
    db.execute = AsyncMock(return_value=result_mock)
    out = await remediation_repo.get_by_id_with_incident_and_project(db, remediation.id)
    assert out is remediation
    db.execute.assert_called_once()
