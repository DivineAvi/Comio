"""Chat routes — REST endpoints for chat sessions and messages.

These endpoints let users:
- Create/list/delete chat sessions
- Send messages and get AI responses
- Load chat history

WebSocket streaming will be added later (Day 21).
For now, we use REST — the response includes all events at once.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import get_current_user
from apps.api.database import get_db
from apps.api.exceptions import NotFoundException, ForbiddenException, ComioException
from apps.api.models.user import User
from apps.api.repositories import project_repo, sandbox_repo
from apps.api.schemas.chat import ChatSessionCreate, ChatMessageSend
from apps.api.services.chat_service import chat_service

router = APIRouter(prefix="/projects/{project_id}/sandbox/chat", tags=["chat"])


# ── Helpers ───────────────────────────────────────────

async def _get_sandbox_for_chat(
    project_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
):
    """Verify project ownership and get the sandbox."""
    project = await project_repo.get_by_id(db, project_id)
    if not project:
        raise NotFoundException("Project", str(project_id))
    if project.owner_id != current_user.id:
        raise ForbiddenException("You don't have access to this project")

    sandbox = await sandbox_repo.get_by_project(db, project_id)
    if not sandbox:
        raise ComioException("No sandbox exists for this project", status_code=404)

    return project, sandbox


# ── Session Routes ────────────────────────────────────

@router.post("/sessions", status_code=201)
async def create_session(
    project_id: uuid.UUID,
    body: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat session for this project's sandbox."""
    project, sandbox = await _get_sandbox_for_chat(project_id, current_user, db)

    session = await chat_service.create_session(
        db,
        sandbox_id=sandbox.id,
        user_id=current_user.id,
        title=body.title,
    )

    return {
        "id": str(session.id),
        "title": session.title,
        "is_active": session.is_active,
        "sandbox_id": str(session.sandbox_id),
        "user_id": str(session.user_id),
        "created_at": session.created_at.isoformat(),
    }


@router.get("/sessions")
async def list_sessions(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all chat sessions for this project's sandbox."""
    project, sandbox = await _get_sandbox_for_chat(project_id, current_user, db)

    sessions = await chat_service.list_sessions(db, sandbox.id)

    return {
        "sessions": [
            {
                "id": str(s.id),
                "title": s.title,
                "is_active": s.is_active,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ],
        "total": len(sessions),
    }


@router.get("/sessions/{session_id}")
async def get_session(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a chat session with all its messages."""
    project, sandbox = await _get_sandbox_for_chat(project_id, current_user, db)

    session = await chat_service.get_session_with_messages(db, session_id)
    if not session:
        raise NotFoundException("ChatSession", str(session_id))
    if session.sandbox_id != sandbox.id:
        raise ForbiddenException("Session does not belong to this sandbox")

    return {
        "id": str(session.id),
        "title": session.title,
        "is_active": session.is_active,
        "sandbox_id": str(session.sandbox_id),
        "created_at": session.created_at.isoformat(),
        "messages": [
            {
                "id": str(m.id),
                "role": m.role.value if hasattr(m.role, 'value') else m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "files_modified": m.files_modified,
                "created_at": m.created_at.isoformat(),
            }
            for m in session.messages
        ],
    }


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat session and all its messages."""
    project, sandbox = await _get_sandbox_for_chat(project_id, current_user, db)

    session = await chat_service.get_session(db, session_id)
    if not session:
        raise NotFoundException("ChatSession", str(session_id))
    if session.sandbox_id != sandbox.id:
        raise ForbiddenException("Session does not belong to this sandbox")

    await chat_service.delete_session(db, session)


# ── Message Routes ────────────────────────────────────

@router.get("/sessions/{session_id}/messages")
async def get_messages(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all messages for a chat session."""
    project, sandbox = await _get_sandbox_for_chat(project_id, current_user, db)

    session = await chat_service.get_session(db, session_id)
    if not session:
        raise NotFoundException("ChatSession", str(session_id))
    if session.sandbox_id != sandbox.id:
        raise ForbiddenException("Session does not belong to this sandbox")

    messages = await chat_service.get_messages(db, session_id)

    return {
        "messages": [
            {
                "id": str(m.id),
                "role": m.role.value if hasattr(m.role, 'value') else m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "files_modified": m.files_modified,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "total": len(messages),
    }


@router.post("/sessions/{session_id}/messages")
async def send_message(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    body: ChatMessageSend,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the AI agent and get a response.

    This is the main chat endpoint. It:
    1. Persists the user message
    2. Runs the AI agent's ReAct loop (may take 5-30 seconds)
    3. Persists the assistant response
    4. Returns all events (tool calls, text, file changes)

    For real-time streaming, WebSocket support comes on Day 21.
    """
    project, sandbox = await _get_sandbox_for_chat(project_id, current_user, db)

    session = await chat_service.get_session(db, session_id)
    if not session:
        raise NotFoundException("ChatSession", str(session_id))
    if session.sandbox_id != sandbox.id:
        raise ForbiddenException("Session does not belong to this sandbox")

    if not sandbox.container_id:
        raise ComioException("Sandbox has no container", status_code=400)

    # This can take a while — the agent may make multiple LLM calls + tool executions
    events = await chat_service.send_message(
        db=db,
        session=session,
        sandbox=sandbox,
        user_message=body.content,
        project_name=project.name,
        project_description=project.description,
        project_type=project.project_type.value if project.project_type else None,
    )

    return {"events": events}