"""Health endpoint — no auth, no DB, no LLM."""
import pytest
from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200


def test_health_status_ok(client: TestClient):
    data = client.get("/health").json()
    assert data["status"] == "ok"
    assert "name" in data
    assert "version" in data


def test_health_name_and_version(client: TestClient):
    data = client.get("/health").json()
    assert isinstance(data["name"], str)
    assert isinstance(data["version"], str)
