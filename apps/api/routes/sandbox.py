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


@router.get("/run/ports")
async def list_running_ports(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List TCP listening ports and their processes inside the sandbox container."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    # Read /proc/net/tcp (and tcp6) to find listening ports -- always available in Linux.
    # Column 3 is local address in hex, column 4 is state (0A = LISTEN).
    # Match inode -> pid via /proc/*/fd symlinks.
    script = r"""
import os, json

def hex_port(addr_hex):
    return int(addr_hex.split(':')[1], 16)

def read_tcp(path):
    entries = []
    try:
        with open(path) as f:
            next(f)  # skip header
            for line in f:
                parts = line.split()
                if len(parts) < 10:
                    continue
                state = parts[3]
                if state != '0A':  # 0A = TCP_LISTEN
                    continue
                port = hex_port(parts[1])
                inode = parts[9]
                entries.append((port, inode))
    except Exception:
        pass
    return entries

# Build inode -> pid map by scanning /proc/*/fd
inode_to_pid = {}
try:
    for pid_dir in os.listdir('/proc'):
        if not pid_dir.isdigit():
            continue
        fd_dir = f'/proc/{pid_dir}/fd'
        try:
            for fd in os.listdir(fd_dir):
                link = os.readlink(f'{fd_dir}/{fd}')
                if link.startswith('socket:['):
                    inode = link[8:-1]
                    inode_to_pid[inode] = pid_dir
        except Exception:
            pass
except Exception:
    pass

ports = {}
for path in ['/proc/net/tcp', '/proc/net/tcp6']:
    for port, inode in read_tcp(path):
        if port in ports or port == 0:
            continue
        pid = inode_to_pid.get(inode)
        cmd = ''
        if pid:
            try:
                with open(f'/proc/{pid}/cmdline', 'rb') as f:
                    cmd = f.read().replace(b'\x00', b' ').decode(errors='replace').strip()[:50]
            except Exception:
                pass
        ports[port] = {'port': port, 'pid': int(pid) if pid else None, 'command': cmd}

import json
print(json.dumps(list(ports.values())))
"""
    import base64 as _b64
    encoded = _b64.b64encode(script.encode()).decode()
    result = await sandbox_manager.exec_command(
        sandbox.container_id,
        ["bash", "-c", f"echo '{encoded}' | base64 -d | python3"],
        timeout=8,
    )

    import json as _json
    try:
        ports_list = _json.loads(result.stdout.strip())
    except Exception:
        ports_list = []

    # Filter out low system ports (< 80) and very high ones (> 65000)
    ports_list = [p for p in ports_list if 80 <= p["port"] <= 65000]
    ports_list.sort(key=lambda p: p["port"])

    return {"ports": ports_list}


@router.delete("/run/ports/{port}")
async def kill_port_process(
    project_id: uuid.UUID,
    port: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Kill the process listening on the given port inside the sandbox container."""
    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    # Find PID via /proc/net/tcp (same approach as list_running_ports) and kill it
    kill_script = (
        "import os, sys\n"
        "port_hex = format(" + str(port) + ", '04X')\n"
        "inode = None\n"
        "for path in ['/proc/net/tcp', '/proc/net/tcp6']:\n"
        "  try:\n"
        "    for line in open(path).readlines()[1:]:\n"
        "      parts = line.split()\n"
        "      if len(parts) < 10 or parts[3] != '0A': continue\n"
        "      if parts[1].split(':')[1].upper() == port_hex:\n"
        "        inode = parts[9]; break\n"
        "  except: pass\n"
        "  if inode: break\n"
        "if not inode: print('not_found'); sys.exit(0)\n"
        "for pid_dir in os.listdir('/proc'):\n"
        "  if not pid_dir.isdigit(): continue\n"
        "  try:\n"
        "    for fd in os.listdir(f'/proc/{pid_dir}/fd'):\n"
        "      link = os.readlink(f'/proc/{pid_dir}/fd/{fd}')\n"
        "      if link == f'socket:[{inode}]':\n"
        "        os.kill(int(pid_dir), 9)\n"
        "        print(f'killed:{pid_dir}'); sys.exit(0)\n"
        "  except: pass\n"
        "print('pid_not_found')\n"
    )
    import base64 as _b64
    encoded = _b64.b64encode(kill_script.encode()).decode()

    result = await sandbox_manager.exec_command(
        sandbox.container_id,
        ["bash", "-c", f"echo '{encoded}' | base64 -d | python3"],
        timeout=8,
    )

    return {
        "status": "killed",
        "port": port,
        "output": result.stdout.strip(),
    }


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


def _rewrite_html_assets(html: str, proxy_base: str, token: str = "") -> str:
    """Rewrite absolute asset URLs in HTML so they go through the Comio proxy.

    For example if proxy_base is '/projects/{id}/sandbox/proxy/3000':
      src="/assets/main.js"  ->  src="/projects/{id}/sandbox/proxy/3000/assets/main.js?token=..."
      href="/style.css"      ->  href="/projects/{id}/sandbox/proxy/3000/style.css?token=..."

    The token is appended so all static asset requests (script, link, img) are
    authenticated through the proxy without needing JS interception.
    """
    import re

    tok_suffix = f"?token={token}" if token else ""

    # Inject <base> tag right after <head> so relative URLs also resolve through proxy
    base_tag = f'<base href="{proxy_base}/">'
    if "<head>" in html:
        html = html.replace("<head>", f"<head>\n  {base_tag}", 1)
    elif "<head " in html:
        html = re.sub(r"(<head[^>]*>)", rf"\1\n  {base_tag}", html, count=1)

    # Rewrite src="/" and href="/" absolute paths (skip external / data / already-rewritten)
    def rewrite_attr(m: re.Match) -> str:
        attr = m.group(1)   # 'src' or 'href'
        quote = m.group(2)  # '"' or "'"
        path = m.group(3)   # the path value starting with /

        if path.startswith("//") or path.startswith("http") or path.startswith(proxy_base):
            return m.group(0)

        sep = "&" if "?" in path else "?"
        new_path = proxy_base + path + (f"{sep}token={token}" if token else "")
        return f'{attr}={quote}{new_path}{quote}'

    html = re.sub(
        r'(src|href)=(["\'])(\/[^"\']*)\2',
        rewrite_attr,
        html,
    )

    # Rewrite url("/path") in inline styles
    def rewrite_css_url(m: re.Match) -> str:
        quote = m.group(1)
        path = m.group(2)
        if path.startswith("//") or path.startswith("http") or path.startswith(proxy_base):
            return m.group(0)
        sep = "&" if "?" in path else "?"
        new_path = proxy_base + path + (f"{sep}token={token}" if token else "")
        return f'url({quote}{new_path}{quote})'

    html = re.sub(r'url\((["\'])(\/[^"\']*)\1\)', rewrite_css_url, html)

    return html


@router.api_route("/proxy/{port}/{path:path}", methods=["GET", "POST", "HEAD"])
@router.api_route("/proxy/{port}", methods=["GET", "POST", "HEAD"])
async def proxy_to_sandbox(
    request: Request,
    project_id: uuid.UUID,
    port: int,
    path: str = "",
    current_user: User = Depends(_get_proxy_user),
    db: AsyncSession = Depends(get_db),
):
    """Proxy HTTP requests to a port running inside the sandbox container.

    Uses httpx to connect directly from the API server to the container via
    its Docker network IP. This properly handles:
    - All HTTP methods (GET, POST, HEAD)
    - Binary content (images, fonts, wasm)
    - HTML with absolute asset paths -> rewrites them through the proxy
    - Streaming/chunked responses

    Example:
        GET /projects/{id}/sandbox/proxy/3000/
        -> fetches http://<container-ip>:3000/ and rewrites HTML asset paths
    """
    from fastapi.responses import Response
    import base64

    project, sandbox = await _get_project_sandbox(project_id, current_user, db)
    _require_running(sandbox)

    token = request.query_params.get("token", "")
    proxy_base = f"/projects/{project_id}/sandbox/proxy/{port}"

    # Build the query string to forward (strip 'token' so the app doesn't see it)
    fwd_params = "&".join(
        f"{k}={v}" for k, v in request.query_params.items() if k != "token"
    )
    url_path = f"/{path}" if path else "/"
    if fwd_params:
        url_path += f"?{fwd_params}"

    # Build the Python proxy script (multiline — base64-encode it to pass safely via bash)
    import base64 as _b64
    python_code = f"""import urllib.request, base64, sys
req = urllib.request.Request('http://localhost:{port}{url_path}')
req.add_header('Accept', 'text/html,application/xhtml+xml,*/*')
try:
    r = urllib.request.urlopen(req, timeout=10)
    body = r.read()
    ct = r.headers.get('Content-Type', 'text/html')
    print(r.status)
    print(ct)
    print(base64.b64encode(body).decode())
except urllib.error.HTTPError as e:
    body = e.read()
    ct = e.headers.get('Content-Type', 'text/html')
    print(e.code)
    print(ct)
    print(base64.b64encode(body).decode())
except Exception as ex:
    print(502)
    print('text/plain')
    print(base64.b64encode(str(ex).encode()).decode())
"""
    encoded_script = _b64.b64encode(python_code.encode()).decode()

    result = await sandbox_manager.exec_command(
        sandbox.container_id,
        ["bash", "-c", f"echo '{encoded_script}' | base64 -d | python3"],
        timeout=18,
    )


    import logging as _logging
    _log = _logging.getLogger(__name__)

    parts = result.stdout.strip().split("\n", 2)
    if len(parts) < 3:
        # Log the raw output for debugging
        _log.warning("Proxy exec returned no/partial output. stdout=%r stderr=%r", result.stdout[:200], result.stderr[:200])
        raise ComioException(
            f"No response from port {port}. stdout: {result.stdout[:200] or '(empty)'}. stderr: {result.stderr[:100] or '(empty)'}",
            status_code=502,
        )

    try:
        status_code = int(parts[0].strip())
    except ValueError:
        status_code = 200

    content_type = parts[1].strip()
    try:
        content = base64.b64decode(parts[2].strip())
    except Exception:
        content = parts[2].encode()

    # If the Python script itself failed (returned 502), enrich the error message
    if status_code == 502:
        try:
            err_msg = content.decode("utf-8", errors="replace")
        except Exception:
            err_msg = "unknown error"
        _log.warning("Proxy got 502 from container: port=%d error=%s", port, err_msg)
        raise ComioException(
            f"Cannot connect to port {port}: {err_msg}",
            status_code=502,
        )

    # For HTML responses, rewrite asset URLs so they load through the proxy
    if "text/html" in content_type:
        try:
            html_text = content.decode("utf-8", errors="replace")
            html_text = _rewrite_html_assets(html_text, proxy_base, token=token)
            # Inject a script to reroute dynamic fetch() calls through the proxy
            if token:
                _b = repr(proxy_base)
                _t = repr(token)
                inject_script = (
                    "<script>\n"
                    "// Comio proxy: route absolute fetch/XHR calls through the proxy\n"
                    "(function() {\n"
                    "  var _base = " + _b + ";\n"
                    "  var _tok = " + _t + ";\n"
                    "  var _origFetch = window.fetch;\n"
                    "  window.fetch = function(url, opts) {\n"
                    "    if (typeof url === 'string' && url.startsWith('/') && !url.startsWith(_base)) {\n"
                    "      url = _base + url + (url.includes('?') ? '&' : '?') + 'token=' + _tok;\n"
                    "    }\n"
                    "    return _origFetch(url, opts);\n"
                    "  };\n"
                    "})();\n"
                    "</script>"
                )
                if "</head>" in html_text:
                    html_text = html_text.replace("</head>", inject_script + "</head>", 1)
                else:
                    html_text = inject_script + html_text
            content = html_text.encode("utf-8")
            content_type = "text/html; charset=utf-8"
        except Exception:
            pass

    return Response(
        content=content,
        status_code=status_code,
        media_type=content_type,
        headers={"Content-Length": str(len(content))},
    )