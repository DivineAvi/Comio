"""Chat repository — database operations for chat sessions and messages."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.chat import ChatSession, ChatMessage, MessageRole
from apps.api.repositories.base import BaseRepository


class ChatSessionRepository(BaseRepository[ChatSession]):
    def __init__(self):
        super().__init__(ChatSession)

    async def get_by_sandbox(
        self, db: AsyncSession, sandbox_id: uuid.UUID
    ) -> list[ChatSession]:
        """Get all chat sessions for a sandbox, newest first."""
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.sandbox_id == sandbox_id)
            .order_by(ChatSession.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_with_messages(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> ChatSession | None:
        """Get a chat session with all its messages eagerly loaded."""
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.id == session_id)
            .options(selectinload(ChatSession.messages))
        )
        return result.scalar_one_or_none()


class ChatMessageRepository(BaseRepository[ChatMessage]):
    def __init__(self):
        super().__init__(ChatMessage)

    async def get_by_session(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> list[ChatMessage]:
        """Get all messages for a session, ordered by creation time."""
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(result.scalars().all())

    async def add_message(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        role: MessageRole,
        content: str,
        tool_calls: dict | None = None,
        files_modified: list[str] | None = None,
    ) -> ChatMessage:
        """Add a message to a chat session."""
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            files_modified=files_modified,
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        return message


# Singletons
chat_session_repo = ChatSessionRepository()
chat_message_repo = ChatMessageRepository()