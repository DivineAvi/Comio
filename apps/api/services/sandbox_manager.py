"""Sandbox Manager — provisions and manages Docker containers per project.

This is the core infrastructure service. It handles:
- Creating containers (for imported repos or blank projects)
- Starting/stopping containers
- Executing commands inside containers
- Volume management for file persistence
- Container cleanup

Every project gets its own isolated Docker container with:
- Its own filesystem (Docker volume)
- Resource limits (CPU, memory)
- Network isolation
- Non-root user

Architecture:
    Project Route → SandboxManager → Docker Engine → Container
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass

import docker
from docker.errors import NotFound, APIError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.models.sandbox import Sandbox, SandboxStatus
from apps.api.models.project import Project

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    """Result of executing a command inside a sandbox container."""
    exit_code: int
    stdout: str
    stderr: str


class SandboxManager:
    """Manages Docker container lifecycle for project sandboxes.

    Usage:
        manager = SandboxManager()
        sandbox = await manager.create_sandbox(db, project)
        result = await manager.exec_command(sandbox.container_id, ["python", "app.py"])
        print(result.stdout)
    """

    def __init__(self):
        # Connect to the Docker daemon (same as running 'docker' in terminal)
        # This uses the local Docker socket by default
        self._client = docker.from_env()

    # ── Container Lifecycle ───────────────────────────

    async def create_sandbox(self, db: AsyncSession, project: Project) -> Sandbox:
        """Create a sandbox for an imported (cloned) project.

        Steps:
        1. Create a named Docker volume for file persistence
        2. Create and start a container from the sandbox image
        3. Clone the project's GitHub repo into /workspace
        4. Save sandbox metadata to the database
        """
        volume_name = f"comio-sandbox-{project.id}"
        container_name = f"comio-sandbox-{str(project.id)[:8]}"

        logger.info("Creating sandbox for project %s (cloned)", project.name)

        # Step 1: Create volume + container (blocking Docker calls → run in thread)
        container = await asyncio.to_thread(
            self._create_container, volume_name, container_name
        )

        # Step 2: Clone the repo if URL exists
        if project.repo_url:
            clone_result = await self.exec_command(
                container.id,
                ["git", "clone", project.repo_url, "."],
                timeout=120,  # Cloning can take a while
            )
            if clone_result.exit_code != 0:
                logger.error("Git clone failed: %s", clone_result.stderr)

        # Step 3: Save to database
        sandbox = Sandbox(
            container_id=container.id,
            status=SandboxStatus.RUNNING,
            volume_name=volume_name,
            git_branch=project.default_branch,
            project_id=project.id,
        )
        db.add(sandbox)
        await db.commit()
        await db.refresh(sandbox)

        logger.info("Sandbox created: %s (container: %s)", sandbox.id, container.short_id)
        return sandbox

    async def create_blank_sandbox(self, db: AsyncSession, project: Project) -> Sandbox:
        """Create a blank sandbox for a new project (created from scratch).

        Steps:
        1. Create a named Docker volume
        2. Create and start a container
        3. Initialize git repo (no clone — AI will create files)
        4. Save to database
        """
        volume_name = f"comio-sandbox-{project.id}"
        container_name = f"comio-sandbox-{str(project.id)[:8]}"

        logger.info("Creating blank sandbox for project %s", project.name)

        container = await asyncio.to_thread(
            self._create_container, volume_name, container_name
        )

        # Initialize empty git repo
        await self.exec_command(container.id, ["git", "init"])

        sandbox = Sandbox(
            container_id=container.id,
            status=SandboxStatus.RUNNING,
            volume_name=volume_name,
            git_branch="main",
            project_id=project.id,
        )
        db.add(sandbox)
        await db.commit()
        await db.refresh(sandbox)

        logger.info("Blank sandbox created: %s (container: %s)", sandbox.id, container.short_id)
        return sandbox

    async def start_sandbox(self, container_id: str) -> None:
        """Start a stopped sandbox container."""
        logger.info("Starting sandbox container: %s", container_id[:12])
        await asyncio.to_thread(self._start_container, container_id)

    async def stop_sandbox(self, container_id: str) -> None:
        """Stop a running sandbox (preserves files on the volume)."""
        logger.info("Stopping sandbox container: %s", container_id[:12])
        await asyncio.to_thread(self._stop_container, container_id)

    async def destroy_sandbox(self, container_id: str, volume_name: str | None = None) -> None:
        """Remove a container and optionally its volume.

        This permanently deletes the container and all its data.
        Use with caution — there's no undo.
        """
        logger.info("Destroying sandbox container: %s", container_id[:12])
        await asyncio.to_thread(self._destroy_container, container_id, volume_name)

    # ── Command Execution ─────────────────────────────

    async def exec_command(
        self,
        container_id: str,
        cmd: list[str],
        timeout: int = 30,
        workdir: str = "/workspace",
    ) -> ExecResult:
        """Execute a command inside a sandbox container.

        This is how the AI agent interacts with the sandbox:
        - Read files:    exec_command(id, ["cat", "app.py"])
        - Write files:   exec_command(id, ["bash", "-c", "echo 'code' > app.py"])
        - Run commands:  exec_command(id, ["pip", "install", "flask"])
        - Run tests:     exec_command(id, ["python", "-m", "pytest"])

        Args:
            container_id: Docker container ID
            cmd: Command as a list of strings
            timeout: Maximum execution time in seconds
            workdir: Working directory inside the container

        Returns:
            ExecResult with exit_code, stdout, stderr
        """
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self._exec_in_container, container_id, cmd, workdir
                ),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("Command timed out after %ds: %s", timeout, " ".join(cmd))
            return ExecResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
            )

    async def get_status(self, container_id: str) -> dict:
        """Get the current status of a sandbox container."""
        try:
            container = await asyncio.to_thread(
                self._client.containers.get, container_id
            )
            return {
                "status": container.status,  # "running", "exited", "paused"
                "short_id": container.short_id,
                "name": container.name,
            }
        except NotFound:
            return {"status": "not_found"}

    async def sync_repo(self, container_id: str, branch: str = "main") -> ExecResult:
        """Git pull latest changes into the sandbox."""
        return await self.exec_command(
            container_id,
            ["git", "pull", "origin", branch],
            timeout=60,
        )

    # ── Private helpers — blocking Docker calls ───────

    def _create_container(self, volume_name: str, container_name: str):
        """Create and start a Docker container (blocking).

        Called via asyncio.to_thread() to not block the event loop.
        """
        # Ensure the sandbox network exists
        self._ensure_network()

        # Create the container
        container = self._client.containers.run(
            image=settings.sandbox_image,       # "comio/sandbox:latest"
            name=container_name,
            detach=True,                         # Run in background
            # Mount a named volume at /workspace for persistence
            volumes={
                volume_name: {"bind": "/workspace", "mode": "rw"},
            },
            # Resource limits
            cpu_count=1,
            mem_limit="512m",
            # Security
            privileged=False,                    # No root-level access to host
            # Networking
            network=settings.sandbox_network,    # Isolated network
            # Labels for easy management
            labels={
                "comio.managed": "true",
                "comio.volume": volume_name,
            },
        )

        logger.info("Container created: %s (%s)", container_name, container.short_id)
        return container

    def _start_container(self, container_id: str) -> None:
        """Start a stopped container (blocking)."""
        container = self._client.containers.get(container_id)
        container.start()

    def _stop_container(self, container_id: str) -> None:
        """Stop a running container (blocking)."""
        try:
            container = self._client.containers.get(container_id)
            container.stop(timeout=10)
        except NotFound:
            logger.warning("Container %s not found (already removed?)", container_id[:12])

    def _destroy_container(self, container_id: str, volume_name: str | None) -> None:
        """Remove container and optionally its volume (blocking)."""
        try:
            container = self._client.containers.get(container_id)
            container.remove(force=True)  # Force removes even if running
            logger.info("Container removed: %s", container_id[:12])
        except NotFound:
            logger.warning("Container %s already removed", container_id[:12])

        # Remove the volume if specified
        if volume_name:
            try:
                volume = self._client.volumes.get(volume_name)
                volume.remove()
                logger.info("Volume removed: %s", volume_name)
            except NotFound:
                logger.warning("Volume %s already removed", volume_name)

    def _exec_in_container(self, container_id: str, cmd: list[str], workdir: str) -> ExecResult:
        """Execute a command inside a container (blocking)."""
        container = self._client.containers.get(container_id)

        # Create and run the exec instance
        exec_result = container.exec_run(
            cmd=cmd,
            workdir=workdir,
            demux=True,  # Separate stdout and stderr
        )

        # demux=True returns (stdout_bytes, stderr_bytes)
        stdout = ""
        stderr = ""
        if exec_result.output:
            if isinstance(exec_result.output, tuple):
                stdout = (exec_result.output[0] or b"").decode("utf-8", errors="replace")
                stderr = (exec_result.output[1] or b"").decode("utf-8", errors="replace")
            else:
                stdout = exec_result.output.decode("utf-8", errors="replace")

        return ExecResult(
            exit_code=exec_result.exit_code,
            stdout=stdout,
            stderr=stderr,
        )

    def _ensure_network(self) -> None:
        """Create the sandbox Docker network if it doesn't exist."""
        try:
            self._client.networks.get(settings.sandbox_network)
        except NotFound:
            self._client.networks.create(
                settings.sandbox_network,
                driver="bridge",
                labels={"comio.managed": "true"},
            )
            logger.info("Created Docker network: %s", settings.sandbox_network)


# Singleton instance
sandbox_manager = SandboxManager()