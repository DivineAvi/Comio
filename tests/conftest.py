"""Pytest fixtures for API and internal tests.

Uses a minimal app with no-op lifespan to avoid Redis/anomaly/LLM.
No real LLM calls; auth and DB can be overridden per test.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.exceptions import ComioException, comio_exception_handler
from apps.api.models.user import User, UserRole
from apps.api.routes import health, remediations
from apps.api.schemas.incident import RemediationApprove, RemediationReject


@asynccontextmanager
async def noop_lifespan(app: FastAPI):
    """Minimal lifespan for tests — no Redis, event bus, or anomaly worker."""
    yield


@pytest.fixture
def test_app() -> FastAPI:
    """FastAPI app with health + remediations; no LLM or external deps."""
    app = FastAPI(lifespan=noop_lifespan)
    app.add_exception_handler(ComioException, comio_exception_handler)
    app.include_router(health.router)
    app.include_router(remediations.router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """TestClient for the minimal test app."""
    return TestClient(test_app)


@pytest.fixture
def operator_user() -> User:
    """User with operator role for approval tests."""
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.OPERATOR
    u.email = "op@test.com"
    return u


@pytest.fixture
def admin_user() -> User:
    """User with admin role."""
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.ADMIN
    u.email = "admin@test.com"
    return u


@pytest.fixture
def viewer_user() -> User:
    """User with viewer role (cannot approve)."""
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.VIEWER
    u.email = "viewer@test.com"
    return u


@pytest.fixture
def remediation_approve_body() -> dict:
    """Valid body for POST remediations/{id}/approve."""
    return RemediationApprove(comment="LGTM").model_dump()


@pytest.fixture
def remediation_reject_body() -> dict:
    """Valid body for POST remediations/{id}/reject."""
    return RemediationReject(reason="Need more context").model_dump()
