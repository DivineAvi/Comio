"""File operations inside sandbox containers.

This service translates high-level file operations into docker exec commands.
It's the bridge between:
  - REST API routes (Day 6) → for the file browser UI
  - AI Chat Agent (Day 7) → for the agent's tools

Architecture:
    Route/Agent → FileOpsService → SandboxManager.exec_command() → Docker container

Security is enforced HERE — path traversal checks, file size limits, binary detection.
"""

import base64
import json
import logging
import posixpath
import httpx

from apps.api.config import settings
from apps.api.services.sandbox_manager import sandbox_manager, ExecResult

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────
WORKSPACE_ROOT = "/workspace"
MAX_FILE_SIZE = 1 * 1024 * 1024    # 1MB — prevent reading huge files
MAX_WRITE_SIZE = 1 * 1024 * 1024   # 1MB — prevent writing huge files


class FileOpsService:
    """File operations inside sandbox containers via docker exec."""

    # ── Security ──────────────────────────────────────

    def _safe_path(self, path: str) -> str:
        """Resolve path and ensure it's within /workspace.

        Accepts:
            "src/main.py"           → "/workspace/src/main.py"
            "./src/main.py"         → "/workspace/src/main.py"
            "/workspace/src/app.py" → "/workspace/src/app.py"
            "."                     → "/workspace"

        Rejects:
            "../../etc/passwd"      → raises ValueError
            "/etc/shadow"           → raises ValueError
        """
        if path.startswith(WORKSPACE_ROOT):
            resolved = posixpath.normpath(path)
        else:
            resolved = posixpath.normpath(posixpath.join(WORKSPACE_ROOT, path))

        # Strict check: must be exactly /workspace or /workspace/...
        if resolved != WORKSPACE_ROOT and not resolved.startswith(WORKSPACE_ROOT + "/"):
            raise ValueError(f"Path traversal detected: {path}")

        return resolved

    # ── File Operations ───────────────────────────────

    async def list_files(
        self, container_id: str, path: str = ".", recursive: bool = False
    ) -> list[dict]:
        """List files and directories at a path inside the sandbox.

        Uses `find` with -printf for structured output.
        Excludes .git/ internals — users don't need to see those.
        """
        safe = self._safe_path(path)

        if recursive:
            cmd = (
                f"find {safe} -not -path '*/\\.git/*' -not -name '.git' "
                f"-printf '%y|%s|%P\\n'"
            )
        else:
            cmd = (
                f"find {safe} -maxdepth 1 -not -path '{safe}' "
                f"-not -path '*/\\.git/*' -not -name '.git' "
                f"-printf '%y|%s|%P\\n'"
            )

        result = await sandbox_manager.exec_command(
            container_id, ["bash", "-c", cmd]
        )

        entries = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) != 3:
                continue
            file_type, size_str, name = parts
            if not name:
                continue
            entries.append({
                "name": posixpath.basename(name),
                "path": name,
                "is_directory": file_type == "d",
                "size": int(size_str) if file_type == "f" else None,
            })

        # Sort: directories first, then alphabetically
        entries.sort(key=lambda e: (not e["is_directory"], e["name"].lower()))
        return entries

    async def read_file(self, container_id: str, path: str) -> dict:
        """Read a text file from the sandbox.

        Security checks:
        1. Path must be under /workspace
        2. File must be < 1MB
        3. File must be text (not binary)
        """
        safe = self._safe_path(path)

        # Step 1: Check file exists and get size
        stat_result = await sandbox_manager.exec_command(
            container_id, ["stat", "--format=%s", safe]
        )
        if stat_result.exit_code != 0:
            raise FileNotFoundError(f"File not found: {path}")

        size = int(stat_result.stdout.strip())
        if size > MAX_FILE_SIZE:
            raise ValueError(f"File too large: {size} bytes (max {MAX_FILE_SIZE})")

        # Step 2: Check if binary
        file_result = await sandbox_manager.exec_command(
            container_id, ["file", "--mime-type", "-b", safe]
        )
        mime = file_result.stdout.strip()
        text_mimes = ("text/", "application/json", "application/xml",
                       "application/javascript", "application/toml",
                       "application/x-yaml")
        if not any(mime.startswith(m) for m in text_mimes):
            raise ValueError(f"Binary file cannot be read as text: {mime}")

        # Step 3: Read content
        cat_result = await sandbox_manager.exec_command(
            container_id, ["cat", safe]
        )
        content = cat_result.stdout
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)

        return {"path": path, "content": content, "size": size, "lines": lines}

    async def write_file(self, container_id: str, path: str, content: str) -> None:
        """Write content to a file in the sandbox.

        Uses base64 encoding to safely transport content with any characters
        (quotes, newlines, special chars) through the shell.
        """
        safe = self._safe_path(path)

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > MAX_WRITE_SIZE:
            raise ValueError(f"Content too large (max {MAX_WRITE_SIZE} bytes)")

        # Ensure parent directory exists
        parent = posixpath.dirname(safe)
        await sandbox_manager.exec_command(container_id, ["mkdir", "-p", parent])

        # Base64 encode → pipe → decode → write
        encoded = base64.b64encode(content_bytes).decode("ascii")
        cmd = f"echo '{encoded}' | base64 -d > {safe}"
        result = await sandbox_manager.exec_command(
            container_id, ["bash", "-c", cmd]
        )

        if result.exit_code != 0:
            raise RuntimeError(f"Failed to write file: {result.stderr}")

        logger.info("File written: %s (%d bytes)", path, len(content_bytes))

    async def create_directory(self, container_id: str, path: str) -> None:
        """Create a directory (and parents) inside the sandbox."""
        safe = self._safe_path(path)
        result = await sandbox_manager.exec_command(
            container_id, ["mkdir", "-p", safe]
        )
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to create directory: {result.stderr}")

    async def delete_file(self, container_id: str, path: str) -> None:
        """Delete a file or empty directory from the sandbox."""
        safe = self._safe_path(path)

        # Safety: never allow deleting /workspace itself
        if safe == WORKSPACE_ROOT:
            raise ValueError("Cannot delete workspace root")

        result = await sandbox_manager.exec_command(
            container_id, ["rm", "-rf", safe]
        )
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to delete: {result.stderr}")

        logger.info("Deleted: %s", path)

    async def search_files(
        self, container_id: str, query: str, glob: str | None = None
    ) -> list[dict]:
        """Search file contents using ripgrep inside the sandbox.

        Returns matches with file path, line number, and matching line content.
        """
        # Escape single quotes in query to prevent shell injection
        safe_query = query.replace("'", "'\\''")

        cmd = f"rg --json --max-count 50 '{safe_query}'"
        if glob:
            safe_glob = glob.replace("'", "'\\''")
            cmd += f" --glob '{safe_glob}'"
        cmd += f" {WORKSPACE_ROOT} 2>/dev/null || true"

        result = await sandbox_manager.exec_command(
            container_id, ["bash", "-c", cmd], timeout=15
        )

        matches = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Ripgrep JSON has type "match" for actual matches
            if entry.get("type") != "match":
                continue

            data = entry.get("data", {})
            match_path = data.get("path", {}).get("text", "")
            line_number = data.get("line_number", 0)
            line_text = data.get("lines", {}).get("text", "").rstrip("\n")

            # Make path relative to workspace
            if match_path.startswith(WORKSPACE_ROOT + "/"):
                match_path = match_path[len(WORKSPACE_ROOT) + 1:]

            matches.append({
                "path": match_path,
                "line_number": line_number,
                "content": line_text,
            })

        return matches

    # ── Git Operations ────────────────────────────────

    async def git_status(self, container_id: str) -> dict:
        """Get parsed git status from the sandbox.

        Uses --porcelain for machine-readable output:
            ## main              ← branch
             M src/main.py       ← modified (unstaged)
            M  src/models.py     ← modified (staged)
            ?? new_file.py       ← untracked
            A  added.py          ← newly staged
        """
        result = await sandbox_manager.exec_command(
            container_id, ["git", "status", "--porcelain", "-b"]
        )

        branch = "main"
        modified = []
        staged = []
        untracked = []

        for line in result.stdout.splitlines():
            if line.startswith("## "):
                # "## main...origin/main" → extract branch name
                branch = line[3:].split("...")[0].strip()
                continue

            if len(line) < 4:
                continue

            index_status = line[0]   # staging area status
            work_status = line[1]    # working directory status
            file_path = line[3:]     # file path

            if index_status == "?" and work_status == "?":
                untracked.append(file_path)
            else:
                if index_status in ("M", "A", "D", "R"):
                    staged.append(file_path)
                if work_status in ("M", "D"):
                    modified.append(file_path)

        has_changes = bool(modified or staged or untracked)
        return {
            "branch": branch,
            "modified": modified,
            "staged": staged,
            "untracked": untracked,
            "has_changes": has_changes,
        }

    async def git_diff(self, container_id: str, file: str | None = None) -> str:
        """Get git diff of changes in the sandbox."""
        cmd = ["git", "diff"]
        if file:
            safe = self._safe_path(file)
            cmd += ["--", safe]

        result = await sandbox_manager.exec_command(container_id, cmd)
        return result.stdout

    async def create_branch(self, container_id: str, branch_name: str) -> None:
        """Create and checkout a new git branch."""
        result = await sandbox_manager.exec_command(
            container_id, ["git", "checkout", "-b", branch_name]
        )
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to create branch: {result.stderr}")

    async def commit_and_push(self, container_id: str, message: str) -> str:
        """Stage all changes, commit, and push. Returns commit SHA."""
        # Stage all changes
        add_result = await sandbox_manager.exec_command(
            container_id, ["git", "add", "-A"]
        )
        if add_result.exit_code != 0:
            raise RuntimeError(f"git add failed: {add_result.stderr}")

        # Commit
        safe_msg = message.replace('"', '\\"')
        commit_result = await sandbox_manager.exec_command(
            container_id, ["git", "commit", "-m", message]
        )
        if commit_result.exit_code != 0:
            raise RuntimeError(f"git commit failed: {commit_result.stderr}")

        # Get commit SHA
        sha_result = await sandbox_manager.exec_command(
            container_id, ["git", "rev-parse", "HEAD"]
        )

        # Push (may fail if no remote — that's OK for created projects)
        push_result = await sandbox_manager.exec_command(
            container_id, ["git", "push", "origin", "HEAD"], timeout=60
        )
        if push_result.exit_code != 0:
            logger.warning("git push failed (no remote?): %s", push_result.stderr)

        return sha_result.stdout.strip()


    async def create_pr(
        self, container_id: str, title: str, body: str, base: str = "main"
    ) -> str:
        """Create a GitHub PR from the current sandbox branch. Uses GITHUB_TOKEN or project token."""
        # 1) Get current branch and remote repo from sandbox
        branch_result = await sandbox_manager.exec_command(container_id, ["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if branch_result.exit_code != 0:
            raise ValueError("Could not get current branch")
        branch = branch_result.stdout.strip()
        remote_result = await sandbox_manager.exec_command(container_id, ["git", "config", "--get", "remote.origin.url"])
        if remote_result.exit_code != 0:
            raise NotImplementedError("No remote.origin.url; push repo first")
        # Parse owner/repo from URL (e.g. https://github.com/owner/repo or git@github.com:owner/repo.git)
        url = remote_result.stdout.strip()
        if "github.com" not in url:
            raise NotImplementedError("Only GitHub remotes supported")
        parts = url.replace(".git", "").rstrip("/").split("/")
        repo_name = parts[-1]
        owner = parts[-2]
        if ":" in owner:
            owner = owner.split(":")[-1]

        token = settings.github_token  # or resolve from project.owner.github_access_token
        if not token:
            raise NotImplementedError("GitHub token required (GITHUB_TOKEN or connect GitHub OAuth)")

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://api.github.com/repos/{owner}/{repo_name}/pulls",
                headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
                json={"title": title, "body": body, "head": branch, "base": base},
            )
            r.raise_for_status()
            data = r.json()
            return data.get("html_url", "")


# Singleton instance
file_ops = FileOpsService()