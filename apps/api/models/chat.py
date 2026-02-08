import uuid

from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum

from apps.api.models.base import BaseModel


class MessageRole(str, Enum):
    """Who sent the message."""
    USER = "user"            # Human user
    ASSISTANT = "assistant"  # AI response
    SYSTEM = "system"        # System prompt / context
    TOOL = "tool"            # Tool call result


class ChatSession(BaseModel):
    __tablename__ = "chat_sessions"

    title: Mapped[str] = mapped_column(String(255), default="New Chat", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Links
    sandbox_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sandboxes.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Relationships
    sandbox: Mapped["Sandbox"] = relationship(back_populates="chat_sessions")
    user: Mapped["User"] = relationship()
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session", order_by="ChatMessage.created_at")


class ChatMessage(BaseModel):
    __tablename__ = "chat_messages"

    role: Mapped[str] = mapped_column(SAEnum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Tool use tracking — stores the tool calls and results as JSON
    tool_calls: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Files the AI modified in this message
    files_modified: Mapped[list | None] = mapped_column(JSON, nullable=True)  # e.g. ["src/main.py", "README.md"]

    # Link to session
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False)

    # Relationships
    session: Mapped["ChatSession"] = relationship(back_populates="messages")
