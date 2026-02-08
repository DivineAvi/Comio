"""Chat schemas for request validation and response serialization."""

import uuid

from pydantic import BaseModel, Field

from apps.api.schemas.base import BaseResponse


# ── Request Schemas ────────────────────────────────────

class ChatSessionCreate(BaseModel):
    """Data to start a new chat session."""
    title: str = Field(default="New Chat", max_length=255)


class ChatMessageSend(BaseModel):
    """A message sent by the user via WebSocket or REST."""
    content: str = Field(min_length=1)


# ── Response Schemas ───────────────────────────────────

class ChatMessageResponse(BaseResponse):
    """A single chat message."""
    role: str           # user, assistant, system, tool
    content: str
    tool_calls: dict | None = None
    files_modified: list | None = None


class ChatSessionResponse(BaseResponse):
    """Chat session metadata."""
    title: str
    is_active: bool
    sandbox_id: uuid.UUID
    user_id: uuid.UUID


class ChatSessionDetailResponse(ChatSessionResponse):
    """Chat session with all messages (for loading history)."""
    messages: list[ChatMessageResponse] = []