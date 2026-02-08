import uuid

from sqlalchemy import String, Text, Float, ForeignKey, Enum as SAEnum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum

from apps.api.models.base import BaseModel


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    DIAGNOSED = "diagnosed"
    FIXING = "fixing"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Incident(BaseModel):
    __tablename__ = "incidents"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(SAEnum(Severity), default=Severity.MEDIUM, nullable=False)
    status: Mapped[str] = mapped_column(SAEnum(IncidentStatus), default=IncidentStatus.OPEN, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)  # "anomaly_detector", "alertmanager", "manual"

    # Alert data — raw data from the observability pipeline
    alert_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Project link
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="incidents")
    diagnosis: Mapped["Diagnosis | None"] = relationship(back_populates="incident", uselist=False)
    remediation: Mapped["Remediation | None"] = relationship(back_populates="incident", uselist=False)


class Diagnosis(BaseModel):
    __tablename__ = "diagnoses"

    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # code_bug, infra, config, dependency, load
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)  # Detailed markdown explanation

    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Supporting data points
    affected_components: Mapped[list | None] = mapped_column(JSON, nullable=True)
    suggested_actions: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # LLM metadata — which model produced this diagnosis
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(nullable=True)

    # Incident link
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id"), unique=True, nullable=False
    )

    # Relationships
    incident: Mapped["Incident"] = relationship(back_populates="diagnosis")


class RemediationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"


class Remediation(BaseModel):
    __tablename__ = "remediations"

    fix_type: Mapped[str] = mapped_column(String(50), nullable=False)  # code_change, config_change, rollback, scale
    diff: Mapped[str] = mapped_column(Text, nullable=False)  # Unified diff format
    files_changed: Mapped[list | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)  # low, medium, high
    status: Mapped[str] = mapped_column(SAEnum(RemediationStatus), default=RemediationStatus.PENDING, nullable=False)

    # PR info — populated after approval and PR creation
    pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(nullable=True)

    # Who approved/rejected
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Incident link
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id"), unique=True, nullable=False
    )

    # Relationships
    incident: Mapped["Incident"] = relationship(back_populates="remediation")
    reviewer: Mapped["User | None"] = relationship()
