"""Webhook routes — receive alerts from external monitoring systems.

These endpoints are called BY Prometheus Alertmanager, not by users.
No authentication required (but in production, add a shared secret).

When an alert arrives:
    1. Parse it into an AlertEvent
    2. Pass to EventService
    3. EventService creates Incident + publishes to event bus
    4. Return 200 OK immediately (don't wait for diagnosis)
"""

import logging

from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from apps.api.database import get_db
from apps.api.services.event_service import event_service
from events.schemas import AlertEvent

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("/alert")
async def receive_alert(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Webhook endpoint for Prometheus Alertmanager.

    Alertmanager sends alerts in this format:
        {
            "version": "4",
            "groupKey": "...",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HighErrorRate",
                        "severity": "critical",
                        "service": "order-api",
                        "comio_project_id": "abc-123"
                    },
                    "annotations": {
                        "summary": "Error rate is above 5%",
                        "description": "Error rate has been above 5% for 5 minutes"
                    },
                    "fingerprint": "abc123def"
                }
            ]
        }

    We extract the first alert and create an incident.
    In production, you'd process all alerts in the batch.
    """
    body = await request.json()

    # Extract alerts from Alertmanager format
    alerts = body.get("alerts", [])
    if not alerts:
        return {"status": "ignored", "reason": "No alerts in payload"}

    # Process the first alert (in production, loop through all)
    alert_data = alerts[0]
    labels = alert_data.get("labels", {})
    annotations = alert_data.get("annotations", {})

    # Extract project ID from labels (Alertmanager rule must set this)
    project_id = labels.get("comio_project_id", "")
    if not project_id:
        logger.warning("Alert missing comio_project_id label — cannot route to project")
        return {"status": "ignored", "reason": "Missing comio_project_id label"}

    # Build AlertEvent
    alert_event = AlertEvent(
        source="alertmanager",
        alert_name=labels.get("alertname", "UnknownAlert"),
        severity=labels.get("severity", "medium"),
        labels=labels,
        annotations=annotations,
        project_id=project_id,
        fingerprint=alert_data.get("fingerprint", ""),
    )

    # Handle the alert (creates incident, publishes to event bus)
    incident = await event_service.handle_alert(db, alert_event)

    if incident:
        return {
            "status": "processed",
            "incident_id": str(incident.id),
            "message": f"Incident created: {incident.title}",
        }
    else:
        return {
            "status": "duplicate",
            "message": "Alert already processed recently",
        }


@router.post("/test-alert")
async def test_alert(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Test endpoint to manually fire an alert (for development).

    This simulates Alertmanager sending an alert, so you can test
    the full pipeline without setting up Prometheus.

    Usage:
        POST /webhooks/test-alert
        Body (optional): {"project_id": "your-project-id-here"}
    """
    # Parse optional body
    body = {}
    try:
        body = await request.json()
    except:
        pass

    project_id = body.get("project_id")
    if not project_id:
        return {
            "status": "error",
            "message": "Please provide a project_id in the request body",
            "example": {"project_id": "abc-123-def"},
        }

    # Create a test AlertEvent
    alert_event = AlertEvent(
        source="manual_test",
        alert_name="TestAlert",
        severity="high",
        labels={"service": "test-service", "instance": "localhost"},
        annotations={"description": "This is a test alert for development"},
        project_id=project_id,
        fingerprint=f"test-{uuid.uuid4()}",  # Unique fingerprint so it's not deduped
    )

    incident = await event_service.handle_alert(db, alert_event)

    if incident:
        return {
            "status": "test_incident_created",
            "incident_id": str(incident.id),
            "title": incident.title,
            "severity": incident.severity.value,
        }
    else:
        return {"status": "error", "message": "Failed to create test incident"}