"""API tests — health and remediations routes; no LLM, minimal deps."""
import pytest
from fastapi.testclient import TestClient


def test_health_ok(client: TestClient):
    """Health endpoint returns 200 and status ok."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "name" in data
    assert "version" in data


def test_remediations_list_requires_auth(client: TestClient):
    """GET /remediations without auth returns 401 or 403."""
    r = client.get("/remediations")
    assert r.status_code in (401, 403)
