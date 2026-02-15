"""Event service — deduplication, routing, and handler orchestration.

This sits between the raw event bus (Redis/Pub/Sub) and your business logic.

Responsibilities:
1. Deduplicate events (don't create duplicate incidents)
2. Route events to appropriate handlers
3. Publish lifecycle events (incident created, diagnosis completed)

Architecture:
    Webhook receives alert
         → EventService.handle_alert()
         → checks Redis: have we seen this fingerprint recently?
         → creates Incident in DB
         → publishes IncidentEvent to "incidents.created" topic
         → RCA Engine (subscriber) picks it up and starts diagnosis
"""

import hashlib
import json
import logging
import uuid
from datetime import timedelta

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models.incident import Incident, Severity, IncidentStatus
from apps.api.repositories import incident_repo

# Lazy imports for event schemas
from events.schemas import AlertEvent, IncidentEvent, EventType

logger = logging.getLogger(__name__)

# Deduplication window — ignore duplicate alerts within this time
DEDUP_WINDOW_SECONDS = 300  # 5 minutes


class EventService:
    """Manages event lifecycle, deduplication, and routing."""

    def __init__(self):
        self._redis_client: redis.Redis | None = None
        self._event_bus = None  # Will be injected by the app on startup

    async def _get_redis(self) -> redis.Redis:
        """Lazy Redis connection for deduplication."""
        if self._redis_client is None:
            self._redis_client = redis.from_url(
                settings.redis_url, decode_responses=True
            )
        return self._redis_client

    def set_event_bus(self, event_bus):
        """Inject the event bus (called during app startup)."""
        self._event_bus = event_bus

    # ── Deduplication ─────────────────────────────────────

    async def _is_duplicate(self, fingerprint: str) -> bool:
        """Check if we've seen this alert fingerprint recently.

        Uses Redis SET with TTL for time-based deduplication.
        Key format: "alert:dedup:{fingerprint}"
        TTL: DEDUP_WINDOW_SECONDS

        Returns:
            True if this is a duplicate (already seen within window)
            False if this is new
        """
        if not fingerprint:
            return False

        redis_client = await self._get_redis()
        key = f"alert:dedup:{fingerprint}"

        # Try to set the key with NX (only if not exists) and EX (expiry)
        was_set = await redis_client.set(
            key, "1", nx=True, ex=DEDUP_WINDOW_SECONDS
        )

        # If was_set is None, key already existed → duplicate
        # If was_set is True, we just created it → new alert
        return was_set is None

    # ── Alert Handling ────────────────────────────────────

    async def handle_alert(
        self, db: AsyncSession, alert_event: AlertEvent
    ) -> Incident | None:
        """Process an incoming alert event.

        Steps:
        1. Check for deduplication
        2. Create Incident in database
        3. Publish IncidentEvent to event bus
        4. Publish DiagnosisRequestedEvent (RCA engine will pick it up)

        Returns:
            The created Incident, or None if it was a duplicate
        """
        # Step 1: Deduplication
        if await self._is_duplicate(alert_event.fingerprint):
            logger.info(
                "Duplicate alert ignored: %s (fingerprint: %s)",
                alert_event.alert_name,
                alert_event.fingerprint[:12],
            )
            return None

        logger.info("New alert: %s (severity: %s)", alert_event.alert_name, alert_event.severity)

        # Step 2: Map alert severity to incident severity
        severity_map = {
            "critical": Severity.CRITICAL,
            "high": Severity.HIGH,
            "medium": Severity.MEDIUM,
            "low": Severity.LOW,
            "info": Severity.INFO,
        }
        severity = severity_map.get(alert_event.severity.lower(), Severity.MEDIUM)

        # Step 3: Create incident
        try:
            project_uuid = uuid.UUID(alert_event.project_id)
        except (ValueError, AttributeError):
            logger.error("Invalid project_id in alert: %s", alert_event.project_id)
            return None

        incident = await incident_repo.create(
            db,
            title=alert_event.alert_name,
            description=alert_event.annotations.get("description", ""),
            severity=severity,
            status=IncidentStatus.OPEN,
            source=alert_event.source,
            alert_data=alert_event.to_dict(),
            project_id=project_uuid,
        )

        logger.info("Incident created: %s (severity: %s)", incident.id, incident.severity.value)

        # Step 4: Publish IncidentEvent
        if self._event_bus:
            incident_event = IncidentEvent(
                event_type=EventType.INCIDENT_CREATED,
                source="event_service",
                incident_id=str(incident.id),
                project_id=str(incident.project_id),
                title=incident.title,
                severity=incident.severity.value,
                status=incident.status.value,
            )
            await self._event_bus.publish("incidents.created", incident_event)
            logger.debug("Published incident event to 'incidents.created'")

        return incident

    # ── Cleanup ───────────────────────────────────────────

    async def close(self):
        """Close Redis connection."""
        if self._redis_client:
            await self._redis_client.close()


# Singleton
event_service = EventService()