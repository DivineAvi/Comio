"""RCA Service — subscribes to incident events and runs diagnosis.

This service:
1. Listens for incident.created events
2. Runs the RCA engine on new incidents
3. Saves the diagnosis to the database
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.database import get_db
from apps.api.models.incident import Incident, Diagnosis as DiagnosisModel, IncidentStatus
from events.bus import BaseEventBus
from events.schemas import IncidentEvent
from rca import RCAEngine

logger = logging.getLogger(__name__)


class RCAService:
    """Service that runs RCA on incidents."""

    def __init__(self, event_bus: Optional[BaseEventBus] = None):
        self.event_bus = event_bus
        self.rca_engine = RCAEngine(
            llm_provider=settings.default_llm_provider,
            llm_model=settings.default_llm_model,
            prometheus_url=settings.prometheus_url,
        )
        self._subscriber_task: Optional[asyncio.Task] = None

    def set_event_bus(self, event_bus: BaseEventBus):
        """Inject event bus after initialization."""
        self.event_bus = event_bus

    async def start_subscriber(self):
        """Start listening for incident.created events."""
        if not self.event_bus:
            logger.warning("Event bus not set, RCA subscriber not starting")
            return

        logger.info("Starting RCA event subscriber...")

        # Subscribe to incident.created events
        await self.event_bus.subscribe("incident.created", self._handle_incident_created)

        logger.info("RCA subscriber is now listening for incident.created events")

    async def _handle_incident_created(self, event_dict: dict):
        """Handle incident.created event by running RCA.
        
        Args:
            event_dict: Event data as a dictionary (from event bus)
        """
        # Extract incident details from event payload
        payload = event_dict.get("payload", {})
        incident_id = payload.get("incident_id")
        incident_title = payload.get("title", "Unknown")
        
        logger.info(
            "RCA subscriber received incident.created: %s (%s)",
            incident_id,
            incident_title,
        )
        
        if not incident_id:
            logger.error("No incident_id in event payload")
            return

        try:
            # Get a database session
            async for db in get_db():
                # Fetch the incident
                result = await db.execute(
                    select(Incident).where(Incident.id == incident_id)
                )
                incident = result.scalar_one_or_none()

                if not incident:
                    logger.error(
                        "Incident %s not found in database, skipping RCA",
                        event.incident_id,
                    )
                    return

                # Run RCA
                logger.info("Running RCA for incident %s...", incident.id)
                diagnosis_result = await self.rca_engine.diagnose(db, incident)

                # Create database Diagnosis model from dataclass
                diagnosis_model = DiagnosisModel(
                    incident_id=incident.id,
                    root_cause=diagnosis_result.root_cause,
                    category=diagnosis_result.category.value,
                    confidence=diagnosis_result.confidence,
                    explanation=diagnosis_result.reasoning,
                    evidence=[e.__dict__ for e in diagnosis_result.evidence],  # Convert Evidence dataclasses to dicts
                    affected_components=diagnosis_result.affected_components,
                    suggested_actions=[a.__dict__ for a in diagnosis_result.suggested_actions],  # Convert Action dataclasses to dicts
                    llm_provider=settings.default_llm_provider,
                    llm_model=settings.default_llm_model,
                )
                
                db.add(diagnosis_model)
                
                # Update incident status
                incident.status = IncidentStatus.DIAGNOSED
                
                await db.commit()

                logger.info(
                    "RCA complete for incident %s: %s (confidence: %.2f)",
                    incident.id,
                    diagnosis_result.category.value,
                    diagnosis_result.confidence,
                )

                break  # Exit the async for loop

        except Exception as e:
            logger.error("Error handling incident.created event: %s", e, exc_info=True)

    async def close(self):
        """Cleanup resources."""
        logger.info("Closing RCA service...")
        await self.rca_engine.close()


# ── Global singleton ──────────────────────────────────

rca_service = RCAService()