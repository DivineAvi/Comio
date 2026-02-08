"""Sandbox schemas for request validation and response serialization."""

import uuid

from pydantic import BaseModel

from apps.api.schemas.base import BaseResponse


# ── Request Schemas ────────────────────────────────────

class SandboxCreate(BaseModel):
    """Config for creating a sandbox (usually auto-created with project)."""
    cpu_limit: int = 1
    memory_limit_mb: int = 512
    disk_limit_mb: int = 2048


class FileWriteRequest(BaseModel):
    """Request to write a file inside a sandbox."""
    content: str


class GitCommitRequest(BaseModel):
    """Request to commit changes in a sandbox."""
    message: str


class GitPRRequest(BaseModel):
    """Request to create a GitHub PR from sandbox changes."""
    title: str
    body: str = ""
    base_branch: str = "main"


# ── Response Schemas ───────────────────────────────────

class SandboxResponse(BaseResponse):
    """Sandbox status and metadata."""
    container_id: str | None = None
    status: str
    git_branch: str
    cpu_limit: int
    memory_limit_mb: int
    disk_limit_mb: int
    project_id: uuid.UUID


class FileEntry(BaseModel):
    """A file or directory inside a sandbox."""
    name: str
    path: str
    is_directory: bool
    size: int | None = None


class FileContent(BaseModel):
    """File content read from a sandbox."""
    path: str
    content: str
    size: int
    lines: int


class GitStatus(BaseModel):
    """Git status of a sandbox."""
    branch: str
    modified: list[str] = []
    staged: list[str] = []
    untracked: list[str] = []
    has_changes: bool = False
