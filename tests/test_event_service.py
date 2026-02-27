"""Event service publish — no Redis/LLM; mock event bus."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.api.services.event_service import event_service


@pytest.mark.asyncio
async def test_publish_no_op_when_no_bus():
    event_service._event_bus = None
    await event_service.publish("test.topic", {"key": "value"})
    # No exception, no call


@pytest.mark.asyncio
async def test_publish_calls_bus_when_set():
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()
    event_service._event_bus = mock_bus
    await event_service.publish("remediations.pending", {"remediation_id": "r-1", "incident_id": "i-1"})
    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args
    assert call_args[0][0] == "remediations.pending"
    event_obj = call_args[0][1]
    assert hasattr(event_obj, "to_dict")
    d = event_obj.to_dict()
    assert d["event_type"] == "remediations.pending"
    assert d["payload"] == {"remediation_id": "r-1", "incident_id": "i-1"}
    assert "timestamp" in d
