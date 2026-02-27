"""Authentication dependencies for FastAPI route protection.

These are "middleware" functions that run BEFORE your endpoint code.
They extract the JWT token, verify it, and load the user from the DB.

Usage in any route:
    @router.get("/projects")
    async def list_projects(current_user: User = Depends(get_current_user)):
        # current_user is guaranteed to be a valid, active user
        # If the token is invalid, FastAPI returns 401 BEFORE reaching here
        ...
"""

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt import decode_access_token
from apps.api.database import get_db
from apps.api.exceptions import UnauthorizedException, ForbiddenException
from apps.api.models.user import User, UserRole
from apps.api.repositories import user_repo

# This tells FastAPI: "Look for the token at the /auth/login endpoint"
# It also creates the 🔒 Authorize button in the Swagger UI (/docs)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from the JWT token.

    This is a dependency chain:
    1. oauth2_scheme extracts the token from "Authorization: Bearer <token>"
    2. decode_access_token verifies the token and gets the user_id
    3. We look up the user in the database
    4. We check the user is still active

    If ANY step fails → 401 Unauthorized
    """
    # Step 1: Decode the token to get user ID
    user_id = decode_access_token(token)
    if user_id is None:
        raise UnauthorizedException("Invalid or expired token")

    # Step 2: Look up the user in the database
    user = await user_repo.get_by_id(db, user_id)
    if user is None:
        raise UnauthorizedException("User not found")

    # Step 3: Check the user account is still active
    if not user.is_active:
        raise UnauthorizedException("User account is deactivated")

    return user

def require_operator_or_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency: current user must be operator or admin (for approval actions)."""
    if current_user.role not in (UserRole.OPERATOR, UserRole.ADMIN):
        raise ForbiddenException("Only operators or admins can perform this action")
    return current_user

def require_role(*allowed_roles: UserRole):
    """Create a dependency that checks the user has one of the allowed roles.

    Usage:
        @router.delete("/users/{id}")
        async def delete_user(
            current_user: User = Depends(require_role(UserRole.ADMIN)),
        ):
            ...  # Only admins can reach this code

    How it works:
        require_role(UserRole.ADMIN) returns a NEW function.
        That function calls get_current_user first, then checks the role.
        This is called a "closure" — a function that creates another function.
    """
    async def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        # Compare enum to enum (user.role from DB is UserRole)
        if current_user.role not in allowed_roles:
            raise ForbiddenException(
                f"This action requires one of these roles: {', '.join(r.value for r in allowed_roles)}"
            )
        return current_user

    return role_checker