"""Incident and remediation request/response schemas — validation only."""
import uuid

import pytest
from pydantic import ValidationError

from apps.api.schemas.incident import (
    IncidentCreate,
    RemediationApprove,
    RemediationReject,
    GenerateFixRequest,
)


def test_incident_create_valid():
    body = IncidentCreate(
        title="High latency",
        description="P95 > 2s",
        severity="high",
        source="manual",
        project_id=uuid.uuid4(),
    )
    assert body.title == "High latency"
    assert body.severity == "high"
    assert body.source == "manual"


def test_incident_create_minimal():
    body = IncidentCreate(title="Bug", project_id=uuid.uuid4())
    assert body.description is None
    assert body.severity == "medium"
    assert body.source == "manual"


def test_incident_create_title_required():
    with pytest.raises(ValidationError):
        IncidentCreate(title="", project_id=uuid.uuid4())


def test_remediation_approve_optional_comment():
    body = RemediationApprove()
    assert body.comment is None
    body = RemediationApprove(comment="LGTM")
    assert body.comment == "LGTM"


def test_remediation_reject_reason_required():
    with pytest.raises(ValidationError):
        RemediationReject(reason="")
    body = RemediationReject(reason="Need more context")
    assert body.reason == "Need more context"


def test_generate_fix_request_optional_code_context():
    body = GenerateFixRequest()
    assert body.code_context == {}
    body = GenerateFixRequest(code_context={"main.py": "print(1)"})
    assert body.code_context["main.py"] == "print(1)"
