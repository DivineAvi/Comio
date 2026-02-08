import uuid

from sqlalchemy import String, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.models.base import BaseModel


class AuditLog(BaseModel):
    """Records every significant action for compliance and debugging.

    Examples:
    - User approved a remediation
    - AI modified a file in a sandbox
    - Deployment was triggered
    - Project was created/deleted
    """
    __tablename__ = "audit_logs"

    action: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "remediation.approved"
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "remediation", "sandbox", "project"
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)  # UUID of the affected resource
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Extra context

    # Who did it (null for system actions)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    user: Mapped["User | None"] = relationship(back_populates="audit_logs")
