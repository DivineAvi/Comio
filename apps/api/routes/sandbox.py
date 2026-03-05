"""Sandbox routes — manage sandbox containers, files, and git for projects.

These endpoints let users:
- Check sandbox status, start/stop
- Browse, read, write, and search files inside the sandbox
- View git status, diffs, create branches, commit, and (later) create PRs
- Execute arbitrary commands (for debugging/testing)
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import get_current_user
from apps.api.database import get_db
from apps.api.exceptions import NotFoundException, ForbiddenException, ComioException
from apps.api.models.user import User
from apps.api.models.sandbox import SandboxStatus
from apps.api.repositories import project_repo, sandbox_repo
from apps.api.schemas.sandbox import (
    ExecCommandRequest, FileWriteRequest, SearchRequest,
    GitCommitRequest, GitBranchRequest, GitPRRequest,
)
from apps.api.services.sandbox_manager import sandbox_manager
from apps.api.services.file_ops_service import file_ops

router = APIRouter(prefix="/projects/{project_id}/sandbox", tags=["sandbox"])


# ── Helpers ───────────────────────────────────────────

async def _get_project_sandbox(
    project_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
):
    """Fetch a project's sandbox after verifying ownership."""
    project = await project_repo.get_by_id(db, project_id)
    if not project:
        raise NotFoundException("Project", str(project_id))
    if project.owner_id != current_user.id:
        raise ForbiddenException("You don't have access to this project")

    sandbox = await sandbox_repo.get_by_project(db, project_id)
    if not sandbox:
        raise ComioException("No sandbox exists for this project", status_code=404)

    return project, sandbox


def _require_running(sandbox):
    """Ensure the sandbox container is running before file/git operations."""
    if not sandbox.container_id:
        raise ComioException("Sandbox has no container", status_code=400)
    if sandbox.status == SandboxStatus.STOPPED:
        raise ComioException("Sandbox is stopped — start it first", status_code=409)


# ── Sandbox Lifecycle ─────────────────────────────────

@router.get("")
async def get_sandbox_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the sandbox status for a project."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)

    container_status = {}
    if sandbox.container_id:
        container_status = await sandbox_manager.get_status(sandbox.container_id)

    return {
        "id": str(sandbox.id),
        "status": sandbox.status,
        "container_id": sandbox.container_id,
        "container_status": container_status.get("status", "unknown"),
        "git_branch": sandbox.git_branch,
        "volume_name": sandbox.volume_name,
        "cpu_limit": sandbox.cpu_limit,
        "memory_limit_mb": sandbox.memory_limit_mb,
    }


@router.post("/start")
async def start_sandbox(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a stopped sandbox container."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)

    if not sandbox.container_id:
        raise ComioException("Sandbox has no container", status_code=400)

    await sandbox_manager.start_sandbox(sandbox.container_id)
    await sandbox_repo.update_status(db, sandbox, SandboxStatus.RUNNING)

    return {"status": "running", "message": "Sandbox started"}


@router.post("/stop")
async def stop_sandbox(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop a running sandbox (preserves all files)."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)

    if not sandbox.container_id:
        raise ComioException("Sandbox has no container", status_code=400)

    await sandbox_manager.stop_sandbox(sandbox.container_id)
    await sandbox_repo.update_status(db, sandbox, SandboxStatus.STOPPED)

    return {"status": "stopped", "message": "Sandbox stopped (files preserved)"}


@router.post("/sync")
async def sync_sandbox(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Git pull latest changes from the remote repository."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    result = await sandbox_manager.sync_repo(sandbox.container_id, sandbox.git_branch)

    return {
        "status": "synced" if result.exit_code == 0 else "error",
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


@router.post("/exec")
async def exec_command(
    project_id: uuid.UUID,
    body: ExecCommandRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a command inside the sandbox container."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    if not body.command.strip():
        raise ComioException("Command is required", status_code=400)

    result = await sandbox_manager.exec_command(
        sandbox.container_id,
        ["bash", "-c", body.command],
        timeout=body.timeout,
    )

    return {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


# ── File Operations ───────────────────────────────────

@router.get("/files")
async def list_files(
    project_id: uuid.UUID,
    path: str = Query(default=".", description="Directory path relative to workspace"),
    recursive: bool = Query(default=False, description="List recursively"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List files and directories inside the sandbox.

    Used by the frontend file browser tree view.
    """
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    try:
        entries = await file_ops.list_files(sandbox.container_id, path, recursive)
    except ValueError as e:
        raise ComioException(str(e), status_code=400)

    return {"path": path, "entries": entries}


@router.get("/files/{file_path:path}")
async def read_file(
    project_id: uuid.UUID,
    file_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Read a file's content from the sandbox.

    The {file_path:path} syntax allows slashes in the URL:
        GET /projects/123/sandbox/files/src/main.py
    """
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    try:
        content = await file_ops.read_file(sandbox.container_id, file_path)
    except FileNotFoundError:
        raise ComioException(f"File not found: {file_path}", status_code=404)
    except ValueError as e:
        raise ComioException(str(e), status_code=400)

    return content


@router.put("/files/{file_path:path}")
async def write_file(
    project_id: uuid.UUID,
    file_path: str,
    body: FileWriteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Write content to a file in the sandbox (creates or overwrites)."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    try:
        await file_ops.write_file(sandbox.container_id, file_path, body.content)
    except ValueError as e:
        raise ComioException(str(e), status_code=400)
    except RuntimeError as e:
        raise ComioException(str(e), status_code=500)

    return {"status": "written", "path": file_path}


@router.delete("/files/{file_path:path}")
async def delete_file(
    project_id: uuid.UUID,
    file_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a file from the sandbox."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    try:
        await file_ops.delete_file(sandbox.container_id, file_path)
    except ValueError as e:
        raise ComioException(str(e), status_code=400)
    except RuntimeError as e:
        raise ComioException(str(e), status_code=500)

    return {"status": "deleted", "path": file_path}


@router.post("/search")
async def search_files(
    project_id: uuid.UUID,
    body: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search file contents inside the sandbox using ripgrep."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    matches = await file_ops.search_files(
        sandbox.container_id, body.query, body.glob
    )

    return {"query": body.query, "matches": matches, "total": len(matches)}


# ── Git Operations ────────────────────────────────────

@router.get("/git/status")
async def git_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get git status of the sandbox (branch, modified, staged, untracked)."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    status = await file_ops.git_status(sandbox.container_id)
    return status


@router.get("/git/diff")
async def git_diff(
    project_id: uuid.UUID,
    file: str | None = Query(default=None, description="Specific file to diff"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get git diff of changes in the sandbox."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    diff_text = await file_ops.git_diff(sandbox.container_id, file)
    status = await file_ops.git_status(sandbox.container_id)
    has_changes = bool(diff_text.strip()) or status.get("has_changes", False)
    return {"diff": diff_text, "has_changes": has_changes}


@router.post("/git/branch")
async def create_branch(
    project_id: uuid.UUID,
    body: GitBranchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create and checkout a new git branch in the sandbox."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    try:
        await file_ops.create_branch(sandbox.container_id, body.branch_name)
    except RuntimeError as e:
        raise ComioException(str(e), status_code=400)

    # Update the sandbox's tracked branch
    await sandbox_repo.update_status(db, sandbox, sandbox.status)
    sandbox.git_branch = body.branch_name
    await db.commit()

    return {"status": "created", "branch": body.branch_name}


@router.post("/git/commit")
async def git_commit(
    project_id: uuid.UUID,
    body: GitCommitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage all changes, commit, and push."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    try:
        sha = await file_ops.commit_and_push(sandbox.container_id, body.message)
    except RuntimeError as e:
        raise ComioException(str(e), status_code=400)

    return {"status": "committed", "sha": sha, "message": body.message}


@router.post("/git/pr")
async def create_pr(
    project_id: uuid.UUID,
    body: GitPRRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a GitHub PR from sandbox changes (requires GitHub OAuth)."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    try:
        pr_url = await file_ops.create_pr(
            sandbox.container_id,
            body.title,
            body.body,
            body.base_branch,
            token=current_user.github_access_token,
        )
    except NotImplementedError as e:
        raise ComioException(str(e), status_code=501)

    return {"status": "created", "pr_url": pr_url}


# ── Run & Port-Forward ────────────────────────────────

@router.post("/run")
async def run_project(
    project_id: uuid.UUID,
    body: ExecCommandRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a long-running process inside the sandbox (e.g. `python app.py`).

    The command runs in the background. Use GET /run/output to stream logs
    (not yet implemented) or GET /proxy/{port} to access the running server.

    Returns the command output captured during a brief 3-second window,
    enough to detect immediate startup errors.
    """
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    # Run the command with a short timeout — if it fails immediately we get the error
    result = await sandbox_manager.exec_command(
        sandbox.container_id,
        ["bash", "-c", f"nohup {body.command} > /tmp/comio_run.log 2>&1 & echo $!"],
        timeout=5,
    )

    pid = result.stdout.strip()
    return {
        "status": "started",
        "pid": pid,
        "log_file": "/tmp/comio_run.log",
        "message": f"Process started in background (PID {pid}). Use View Logs or open the preview URL.",
    }


@router.get("/run/logs")
async def get_run_logs(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest stdout/stderr from the background run process."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    result = await sandbox_manager.exec_command(
        sandbox.container_id,
        ["bash", "-c", "tail -100 /tmp/comio_run.log 2>/dev/null || echo '(no logs yet)'"],
        timeout=5,
    )
    return {"logs": result.stdout}


async def _get_proxy_user(
    request: Request,
    token: str = Query(None),
    db: AsyncSession = Depends(get_db)
) -> User:
    from apps.api.exceptions import UnauthorizedException
    from apps.api.auth.jwt import decode_access_token
    from apps.api.repositories import user_repo

    if not token:
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ")[1]

    if not token:
        raise UnauthorizedException("No token provided via header or query ?token=")

    user_id = decode_access_token(token)
    if not user_id:
        raise UnauthorizedException("Invalid or expired token")

    user = await user_repo.get_by_id(db, user_id)
    if not user or not user.is_active:
        raise UnauthorizedException("User not found or inactive")

    return user

@router.get("/proxy/{port}/{path:path}")
@router.get("/proxy/{port}")
async def proxy_to_sandbox(
    project_id: uuid.UUID,
    port: int,
    path: str = "",
    current_user: User = Depends(_get_proxy_user),
    db: AsyncSession = Depends(get_db),
):
    """Proxy an HTTP GET request to a port running inside the sandbox.

    This lets users preview their running app through Comio without exposing
    Docker ports directly. Uses `docker exec curl` to make the request from
    inside the container network.

    Example: GET /projects/{id}/sandbox/proxy/3000/ → http://localhost:3000/ inside the container
    """
    from fastapi.responses import Response
    import json as _json

    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    url = f"http://localhost:{port}/{path}"
    # Use curl inside the container to fetch the page
    result = await sandbox_manager.exec_command(
        sandbox.container_id,
        [
            "curl", "-s", "-i",
            "--max-time", "10",
            "--location",
            "-H", "Accept: text/html,application/json,*/*",
            url,
        ],
        timeout=15,
    )

    if result.exit_code != 0:
        raise ComioException(
            f"Could not reach port {port} inside sandbox. Is your app running? "
            f"Error: {result.stderr or result.stdout or 'timeout/connection refused'}",
            status_code=502,
        )

    # Parse curl -i output: headers\r\n\r\nbody
    raw = result.stdout
    if "\r\n\r\n" in raw:
        header_part, body = raw.split("\r\n\r\n", 1)
    elif "\n\n" in raw:
        header_part, body = raw.split("\n\n", 1)
    else:
        header_part, body = "", raw

    # Extract status code from first line (e.g. "HTTP/1.1 200 OK")
    status_code = 200
    content_type = "text/html; charset=utf-8"
    for line in header_part.splitlines():
        if line.startswith("HTTP/"):
            try:
                status_code = int(line.split()[1])
            except (IndexError, ValueError):
                pass
        if line.lower().startswith("content-type:"):
            content_type = line.split(":", 1)[1].strip()

    return Response(
        content=body.encode("utf-8", errors="replace"),
        status_code=status_code,
        media_type=content_type,
    )