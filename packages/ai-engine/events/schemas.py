"""Event schemas — standardized data structures flowing through the event pipeline.

These are NOT database models. They're lightweight dataclasses that represent
events passing between services via the event bus (Redis Pub/Sub or Cloud Pub/Sub).

Think of them as "messages" between services:
    Alertmanager → AlertEvent → EventBus → EventService → creates Incident

Each event has:
- id: unique identifier (for deduplication)
- timestamp: when the event occurred
- source: who/what generated it
- payload: the actual data
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class EventType(str, Enum):
    """Types of events in the Comio pipeline."""
    # Alert lifecycle
    ALERT_RECEIVED = "alert.received"          # Raw alert from Alertmanager/external
    ALERT_ENRICHED = "alert.enriched"          # Alert with added context (metrics, logs)

    # Incident lifecycle
    INCIDENT_CREATED = "incident.created"      # New incident created from alert
    INCIDENT_UPDATED = "incident.updated"      # Incident status changed

    # Diagnosis lifecycle
    DIAGNOSIS_REQUESTED = "diagnosis.requested"  # RCA engine should analyze this
    DIAGNOSIS_COMPLETED = "diagnosis.completed"  # RCA finished, diagnosis available

    # Remediation lifecycle
    REMEDIATION_PROPOSED = "remediation.proposed"  # Fix generated, awaiting approval
    REMEDIATION_APPROVED = "remediation.approved"  # Human approved the fix
    REMEDIATION_APPLIED = "remediation.applied"    # Fix was applied (PR created, deployed)

    # Deploy lifecycle
    DEPLOY_STARTED = "deploy.started"
    DEPLOY_COMPLETED = "deploy.completed"
    DEPLOY_FAILED = "deploy.failed"

    # Metric events (from anomaly detector)
    METRIC_ANOMALY = "metric.anomaly"          # Anomaly detected in metrics


@dataclass
class BaseEvent:
    """Base event — all events inherit from this.

    Every event has a unique ID (for deduplication), a type, a timestamp,
    and a source (which service/component generated it).
    """
    source: str                                          # "alertmanager", "anomaly_detector", "api", etc.
    event_type: EventType = None                         # Set by subclasses in __post_init__
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)         # Extra context (request_id, user_id, etc.)

    def to_dict(self) -> dict:
        """Serialize for JSON transport over the event bus."""
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "source": self.source,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "payload": self._payload_dict(),
        }

    def _payload_dict(self) -> dict:
        """Override in subclasses to add event-specific data."""
        return {}


@dataclass
class AlertEvent(BaseEvent):
    """Alert from Alertmanager or external monitoring.

    This is what Prometheus Alertmanager sends when an alert fires:
    - alert_name: e.g. "HighErrorRate", "LatencySpike"
    - severity: critical/high/medium/low
    - labels: Prometheus labels (service, instance, etc.)
    - annotations: human-readable description, runbook URL
    - project_id: which Comio project this alert belongs to

    Example from Alertmanager:
        {
            "alert_name": "HighErrorRate",
            "severity": "critical",
            "labels": {"service": "order-api", "instance": "10.0.0.1:8080"},
            "annotations": {"description": "Error rate > 5% for 5 minutes"},
            "project_id": "abc-123"
        }
    """
    alert_name: str = ""
    severity: str = "medium"                # critical, high, medium, low
    labels: dict = field(default_factory=dict)
    annotations: dict = field(default_factory=dict)
    project_id: str = ""                    # Which Comio project this belongs to
    fingerprint: str = ""                   # Alertmanager dedup key

    def __post_init__(self):
        self.event_type = EventType.ALERT_RECEIVED

    def _payload_dict(self) -> dict:
        return {
            "alert_name": self.alert_name,
            "severity": self.severity,
            "labels": self.labels,
            "annotations": self.annotations,
            "project_id": self.project_id,
            "fingerprint": self.fingerprint,
        }


@dataclass
class IncidentEvent(BaseEvent):
    """Event emitted when an incident is created or updated."""
    incident_id: str = ""
    project_id: str = ""
    title: str = ""
    severity: str = "medium"
    status: str = "open"

    def _payload_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "project_id": self.project_id,
            "title": self.title,
            "severity": self.severity,
            "status": self.status,
        }


@dataclass
class DiagnosisEvent(BaseEvent):
    """Event emitted when a diagnosis is requested or completed."""
    incident_id: str = ""
    project_id: str = ""
    root_cause: str = ""
    confidence: float = 0.0
    category: str = ""

    def _payload_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "project_id": self.project_id,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "category": self.category,
        }


@dataclass
class MetricEvent(BaseEvent):
    """Event from the anomaly detector when it finds an anomaly."""
    metric_name: str = ""                  # e.g. "http_request_duration_seconds"
    value: float = 0.0
    threshold: float = 0.0
    anomaly_score: float = 0.0             # 0.0 = normal, 1.0 = very anomalous
    project_id: str = ""
    labels: dict = field(default_factory=dict)

    def __post_init__(self):
        self.event_type = EventType.METRIC_ANOMALY

    def _payload_dict(self) -> dict:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "threshold": self.threshold,
            "anomaly_score": self.anomaly_score,
            "project_id": self.project_id,
            "labels": self.labels,
        }


@dataclass
class DeployEvent(BaseEvent):
    """Event from the deploy service."""
    project_id: str = ""
    deployment_id: str = ""
    status: str = ""                       # building, deploying, running, failed
    deploy_url: str = ""
    image_tag: str = ""
    error: str = ""

    def _payload_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "deployment_id": self.deployment_id,
            "status": self.status,
            "deploy_url": self.deploy_url,
            "image_tag": self.image_tag,
            "error": self.error,
        }