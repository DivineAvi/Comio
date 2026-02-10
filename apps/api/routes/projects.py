"""Project routes — import repos, create new projects, list, get, update, delete.

All routes are protected — require a valid JWT token.
Users can only access their OWN projects.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from logging import getLogger
from apps.api.auth import get_current_user
from apps.api.database import get_db
from apps.api.exceptions import NotFoundException, ForbiddenException
from apps.api.models.project import Project, ProjectOrigin, ProjectType
from apps.api.models.user import User
from apps.api.repositories import project_repo
from apps.api.services.sandbox_manager import sandbox_manager
from apps.api.schemas.project import (
    ProjectImport,
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectListResponse,
)

router = APIRouter(prefix="/projects", tags=["projects"])

logger = getLogger(__name__)
# ── Helper ────────────────────────────────────────────

def _project_to_response(project: Project) -> ProjectResponse:
    """Convert a Project model to a ProjectResponse schema.

    This avoids repeating the same field mapping in every route.
    """
    return ProjectResponse(
        id=project.id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        name=project.name,
        description=project.description,
        origin=project.origin,
        project_type=project.project_type,
        repo_url=project.repo_url,
        repo_full_name=project.repo_full_name,
        default_branch=project.default_branch,
        owner_id=project.owner_id,
        monitoring_config=project.monitoring_config,
    )


async def _get_user_project(
    project_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Project:
    """Fetch a project and verify the current user owns it.

    Used by get, update, delete routes to avoid repeating
    the same "fetch + ownership check" logic.
    """
    project = await project_repo.get_by_id(db, project_id)
    if not project:
        raise NotFoundException("Project", str(project_id))
    if project.owner_id != current_user.id:
        raise ForbiddenException("You don't have access to this project")
    return project


# ── Routes ────────────────────────────────────────────

@router.post("/import", response_model=ProjectResponse, status_code=201)
async def import_project(
    body: ProjectImport,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import an existing GitHub repository as a Comio project.

    What happens:
    1. Parse the repo URL to extract owner/repo name
    2. Create a Project record with origin="cloned"
    3. (Future: Day 5) SandboxManager will clone the repo into a Docker container

    Example:
        POST /projects/import
        { "repo_url": "https://github.com/user/my-api" }
    """
    # Extract repo name from URL if name not provided
    # "https://github.com/user/my-api" → "my-api"
    repo_name = body.repo_url.rstrip("/").split("/")[-1]
    # "https://github.com/user/my-api" → "user/my-api"
    repo_full_name = "/".join(body.repo_url.rstrip("/").split("/")[-2:])

    project = await project_repo.create(
        db,
        name=body.name or repo_name,
        description=body.description,
        origin=ProjectOrigin.CLONED,
        project_type=ProjectType.OTHER,
        repo_url=body.repo_url,
        repo_full_name=repo_full_name,
        owner_id=current_user.id,
    )

    # Clone the repo into a sandbox container
    try:
        await sandbox_manager.create_sandbox(db, project)
    except Exception as e:
        logger.warning("Sandbox creation failed (will retry later): %s", e)

    return _project_to_response(project)


@router.post("/create", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a brand new project from scratch.

    What happens:
    1. Create a Project record with origin="created"
    2. (Future: Day 5) SandboxManager will create a blank sandbox with git init
    3. (Future: Day 7) The AI chat agent will scaffold the project

    Example:
        POST /projects/create
        { "name": "todo-api", "description": "A REST API for managing todos", "project_type": "api" }
    """
    project = await project_repo.create(
        db,
        name=body.name,
        description=body.description,
        origin=ProjectOrigin.CREATED,
        project_type=body.project_type,
        owner_id=current_user.id,
    )

    # Create a blank sandbox container (AI will scaffold files later)
    try:
        await sandbox_manager.create_blank_sandbox(db, project)
    except Exception as e:
        logger.warning("Sandbox creation failed (will retry later): %s", e)

    return _project_to_response(project)


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    skip: int = Query(default=0, ge=0, description="Number of projects to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Max projects to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all projects owned by the current user.

    Supports pagination:
        GET /projects?skip=0&limit=20   → first 20 projects
        GET /projects?skip=20&limit=20  → next 20 projects
    """
    projects = await project_repo.get_by_owner(db, current_user.id, skip=skip, limit=limit)
    total = await project_repo.count_by_owner(db, current_user.id)

    return ProjectListResponse(
        projects=[_project_to_response(p) for p in projects],
        total=total,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a single project.

    Returns 404 if not found, 403 if you don't own it.
    """
    project = await _get_user_project(project_id, current_user, db)
    return _project_to_response(project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a project's settings.

    Only sends fields that are provided (partial update).
    """
    project = await _get_user_project(project_id, current_user, db)

    # Only update fields that were actually sent (not None)
    update_data = body.model_dump(exclude_unset=True)
    if update_data:
        project = await project_repo.update(db, project, **update_data)

    return _project_to_response(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project and its resources.

    Returns 204 No Content on success (no response body).

    TODO (Day 5): Also destroy the sandbox container and volume.
    """
    project = await _get_user_project(project_id, current_user, db)

    # TODO (Day 5): Destroy sandbox first
    # if project.sandbox:
    #     await sandbox_manager.destroy_sandbox(project.sandbox.container_id)

    await project_repo.delete(db, project)