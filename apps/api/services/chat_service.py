"""Chat service — orchestrates chat sessions, message persistence, and the AI agent.

This is the glue layer:
    Route receives message → ChatService → persists message → calls Agent → persists response → returns events

Why a service layer?
    - Routes should be thin (just HTTP handling)
    - The agent shouldn't know about databases
    - The service coordinates everything: DB, agent, sandbox, LLM

Architecture:
    Route → ChatService → SandboxChatAgent → LLM + Tools → Sandbox Container
              ↕                                    ↕
           Database                           FileOpsService
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models.chat import ChatSession, ChatMessage, MessageRole
from apps.api.models.sandbox import Sandbox
from apps.api.repositories.chat import chat_session_repo, chat_message_repo

# Lazy imports to avoid circular dependencies at module level
# These are imported inside methods instead

logger = logging.getLogger(__name__)


class ChatService:
    """Manages chat sessions and routes messages to the AI agent."""

    # ── Session Management ────────────────────────────

    async def create_session(
        self,
        db: AsyncSession,
        sandbox_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str = "New Chat",
    ) -> ChatSession:
        """Create a new chat session for a sandbox."""
        session = await chat_session_repo.create(
            db,
            sandbox_id=sandbox_id,
            user_id=user_id,
            title=title,
        )
        logger.info("Chat session created: %s", session.id)
        return session

    async def get_session(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> ChatSession | None:
        """Get a session by ID."""
        return await chat_session_repo.get_by_id(db, session_id)

    async def get_session_with_messages(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> ChatSession | None:
        """Get a session with all messages loaded."""
        return await chat_session_repo.get_with_messages(db, session_id)

    async def list_sessions(
        self, db: AsyncSession, sandbox_id: uuid.UUID
    ) -> list[ChatSession]:
        """List all chat sessions for a sandbox."""
        return await chat_session_repo.get_by_sandbox(db, sandbox_id)

    async def delete_session(
        self, db: AsyncSession, session: ChatSession
    ) -> None:
        """Delete a chat session and all its messages."""
        await chat_session_repo.delete(db, session)

    async def get_messages(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> list[ChatMessage]:
        """Get all messages for a session."""
        return await chat_message_repo.get_by_session(db, session_id)

    # ── Message Processing ────────────────────────────

    async def send_message(
        self,
        db: AsyncSession,
        session: ChatSession,
        sandbox: Sandbox,
        user_message: str,
        project_name: str = "project",
        project_description: str | None = None,
        project_type: str | None = None,
    ) -> list[dict]:
        """Process a user message through the AI agent.

        This is the main entry point for chat:
        1. Persist the user message
        2. Load conversation history from DB
        3. Create the LLM adapter and agent
        4. Run the agent's ReAct loop
        5. Persist the assistant's response
        6. Return events for the frontend

        Returns:
            List of ChatEvent dicts for the frontend
        """
        # Step 1: Persist user message
        await chat_message_repo.add_message(
            db, session.id, MessageRole.USER, user_message
        )

        # Step 2: Load conversation history
        db_messages = await chat_message_repo.get_by_session(db, session.id)
        conversation_history = self._db_messages_to_llm_messages(db_messages[:-1])
        # We exclude the last message (the one we just added) because
        # the agent adds it separately as the current user_message

        # Step 3: Create agent with LLM adapter
        agent = self._create_agent()
        

        # Step 4: Run the ReAct loop
        if not sandbox.container_id:
            return [{"type": "error", "content": "Sandbox has no container"}]

        try:
            events = await agent.process_message(
                container_id=sandbox.container_id,
                conversation_history=conversation_history,
                user_message=user_message,
                project_name=project_name,
                project_description=project_description,
                project_type=project_type,
            )
        except Exception as e:
            logger.error("Agent error: %s", e)
            return [
                {"type": "error", "content": f"AI agent error: {str(e)}"},
                {"type": "done", "files_modified": []},
            ]

        # Step 5: Persist the assistant's response
        # Collect the text response and files modified
        assistant_text = ""
        all_files_modified = []
        all_tool_calls = []

        for event in events:
            event_dict = event.to_dict()
            if event_dict.get("type") == "text":
                assistant_text += event_dict.get("content", "")
            if event_dict.get("type") == "tool_call":
                all_tool_calls.append({
                    "tool": event_dict.get("tool"),
                    "args": event_dict.get("args"),
                })
            if event_dict.get("type") == "done":
                all_files_modified = event_dict.get("files_modified", [])

        if assistant_text:
            await chat_message_repo.add_message(
                db,
                session.id,
                MessageRole.ASSISTANT,
                assistant_text,
                tool_calls=all_tool_calls if all_tool_calls else None,
                files_modified=all_files_modified if all_files_modified else None,
            )

        # Step 6: Return events as dicts for JSON serialization
        return [event.to_dict() for event in events]

    # ── Private Helpers ───────────────────────────────

    def _create_agent(self):
        """Create a SandboxChatAgent with the configured LLM adapter.

        Uses lazy imports to avoid circular dependencies.
        The adapter is created fresh each time based on current settings.
        """
        from adapters.factory import AdapterFactory
        from chat_agent.agent import SandboxChatAgent
        from apps.api.services.file_ops_service import file_ops
        from apps.api.services.sandbox_manager import sandbox_manager

        # Create the LLM adapter from settings
        llm_adapter = AdapterFactory.create(
            provider=settings.default_llm_provider,
            api_key=self._get_api_key(),
            model=settings.default_llm_model,
        )

        return SandboxChatAgent(
            llm_adapter=llm_adapter,
            file_ops=file_ops,
            sandbox_manager=sandbox_manager,
        )

    def _get_api_key(self) -> str:
        """Get the API key for the configured LLM provider."""
        provider = settings.default_llm_provider
        if provider == "openai":
            return settings.openai_api_key
        elif provider == "anthropic":
            return settings.anthropic_api_key
        else:
            return ""  # Ollama doesn't need an API key

    def _db_messages_to_llm_messages(self, db_messages: list[ChatMessage]) -> list:
        """Convert database ChatMessage objects to LLM Message format.

        The agent expects adapters.base.Message objects.
        The DB stores ChatMessage objects.
        This bridges the two.
        """
        from adapters.base import Message

        messages = []
        for msg in db_messages:
            messages.append(Message(
                role=msg.role.value if hasattr(msg.role, 'value') else msg.role,
                content=msg.content,
            ))
        return messages


# Singleton
chat_service = ChatService()