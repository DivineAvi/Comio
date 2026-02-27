"""Fix service — generate_fix_for_incident with mocked FixGenerator (no LLM)."""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.incident import Incident, Diagnosis, Remediation, RemediationStatus
from apps.api.services.fix_service import generate_fix_for_incident


@pytest.fixture
def mock_incident_with_diagnosis():
    """Incident with diagnosis, no remediation."""
    incident = MagicMock(spec=Incident)
    incident.id = uuid4()
    incident.project_id = uuid4()
    incident.diagnosis = MagicMock(spec=Diagnosis)
    incident.diagnosis.root_cause = "DB pool exhausted"
    incident.diagnosis.category = "config"
    incident.diagnosis.confidence = 0.85
    incident.diagnosis.explanation = "Increase pool size."
    incident.diagnosis.suggested_actions = []
    incident.remediation = None
    return incident


@pytest.fixture
def mock_fix_result():
    result = MagicMock()
    result.fix_type = "config_change"
    result.diff = "--- a/config.py\n+++ b/config.py\n"
    result.files_changed = ["config.py"]
    result.explanation = "Increase pool size."
    result.risk_level = "low"
    result.test_suggestions = ["Run load test"]
    return result


@pytest.mark.asyncio
async def test_generate_fix_raises_when_incident_not_found(mock_incident_with_diagnosis):
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    with pytest.raises(ValueError, match="not found"):
        await generate_fix_for_incident(db, mock_incident_with_diagnosis.id, code_context=None)


@pytest.mark.asyncio
async def test_generate_fix_raises_when_no_diagnosis(mock_incident_with_diagnosis):
    mock_incident_with_diagnosis.diagnosis = None
    db = MagicMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=mock_incident_with_diagnosis)
    db.execute = AsyncMock(return_value=result_mock)
    with pytest.raises(ValueError, match="no diagnosis"):
        await generate_fix_for_incident(db, mock_incident_with_diagnosis.id, code_context=None)


@pytest.mark.asyncio
async def test_generate_fix_raises_when_remediation_exists(mock_incident_with_diagnosis):
    mock_incident_with_diagnosis.remediation = MagicMock()
    db = MagicMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=mock_incident_with_diagnosis)
    db.execute = AsyncMock(return_value=result_mock)
    with pytest.raises(ValueError, match="already has a remediation"):
        await generate_fix_for_incident(db, mock_incident_with_diagnosis.id, code_context=None)


@pytest.mark.asyncio
async def test_generate_fix_creates_remediation_and_publishes_event(
    mock_incident_with_diagnosis, mock_fix_result
):
    db = MagicMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=mock_incident_with_diagnosis)
    db.execute = AsyncMock(return_value=result_mock)
    db.add = MagicMock()

    with patch("fix_generator.FixGenerator") as MockFixGen:
        MockFixGen.return_value.generate = AsyncMock(return_value=mock_fix_result)
        with patch("apps.api.services.event_service.event_service") as mock_evt:
            mock_evt.publish = AsyncMock()
            remediation = await generate_fix_for_incident(db, mock_incident_with_diagnosis.id, code_context=None)

    assert remediation is not None
    assert remediation.incident_id == mock_incident_with_diagnosis.id
    assert remediation.fix_type == mock_fix_result.fix_type
    assert remediation.diff == mock_fix_result.diff
    assert remediation.risk_level == mock_fix_result.risk_level
    assert remediation.status == RemediationStatus.PENDING
    db.add.assert_called_once()
    mock_evt.publish.assert_called_once()
    call_payload = mock_evt.publish.call_args[0][1]
    assert "remediation_id" in call_payload
    assert call_payload["incident_id"] == str(mock_incident_with_diagnosis.id)
    assert call_payload["project_id"] == str(mock_incident_with_diagnosis.project_id)
