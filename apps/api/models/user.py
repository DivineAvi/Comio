import uuid
from datetime import datetime

from sqlalchemy import String, Enum as SAEnum, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum

from apps.api.models.base import BaseModel



class UserRole(str, Enum):
    """What a user is allowed to do.

    - viewer: can see dashboards and incidents (read-only)
    - operator: can approve/reject fixes, manage projects
    - admin: full access including settings and user management
    """
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Null if using OAuth only
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(SAEnum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # GitHub OAuth — populated when user connects their GitHub account
    github_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    github_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # Encrypted in production

    # Avatar URL from GitHub
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships — SQLAlchemy loads these automatically when accessed
    # "back_populates" creates a two-way link (user.projects ↔ project.owner)
    projects: Mapped[list["Project"]] = relationship(back_populates="owner")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")