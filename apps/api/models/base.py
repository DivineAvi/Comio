import uuid
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database import Base

class BaseModel(Base):
    """Abstract base model with common fields for all tables.

    Every model inherits from this, so they all get:
    - id: a unique UUID primary key
    - created_at: timestamp set automatically on creation
    - updated_at: timestamp updated automatically on every change

    'abstract = True' means SQLAlchemy won't create a table for BaseModel
    itself — only for its children (User, Project, etc.).
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # Database sets this, not Python
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),  # Automatically updates when the row changes
        nullable=False,
    )