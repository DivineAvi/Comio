"""Remediations API — list, approve, reject, apply; auth and role checks."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.database import get_db
from apps.api.models.user import User, UserRole


def test_remediations_list_requires_auth(client: TestClient):
    r = client.get("/remediations")
    assert r.status_code in (401, 403)


def test_remediations_list_returns_200_with_auth_and_empty_list(client: TestClient, operator_user: User):
    async def override_get_db():
        yield MagicMock()

    async def override_get_current_user():
        return operator_user

    from apps.api.auth import get_current_user
    from apps.api.routes import remediations as remediations_module
    client.app.dependency_overrides[get_db] = override_get_db
    client.app.dependency_overrides[get_current_user] = override_get_current_user
    with patch.object(remediations_module.remediation_repo, "list_pending_for_user", new_callable=AsyncMock, return_value=[]):
        try:
            r = client.get("/remediations")
            assert r.status_code == 200
            assert isinstance(r.json(), list)
            assert r.json() == []
        finally:
            client.app.dependency_overrides.clear()


def test_remediations_approve_requires_auth(client: TestClient):
    r = client.post(f"/remediations/{uuid.uuid4()}/approve", json={"comment": "ok"})
    assert r.status_code in (401, 403)


def test_remediations_reject_requires_auth(client: TestClient):
    r = client.post(f"/remediations/{uuid.uuid4()}/reject", json={"reason": "no"})
    assert r.status_code in (401, 403)


def test_remediations_apply_requires_auth(client: TestClient):
    r = client.post(f"/remediations/{uuid.uuid4()}/apply")
    assert r.status_code in (401, 403)


def test_remediations_list_query_params(client: TestClient, operator_user: User):
    async def override_get_db():
        yield MagicMock()

    async def override_get_current_user():
        return operator_user

    from apps.api.auth import get_current_user
    from apps.api.routes import remediations as remediations_module
    client.app.dependency_overrides[get_db] = override_get_db
    client.app.dependency_overrides[get_current_user] = override_get_current_user
    with patch.object(remediations_module.remediation_repo, "list_pending_for_user", new_callable=AsyncMock, return_value=[]):
        try:
            r = client.get("/remediations?status=pending&skip=0&limit=10&include_expired=false")
            assert r.status_code == 200
            assert isinstance(r.json(), list)
        finally:
            client.app.dependency_overrides.clear()
