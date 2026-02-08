"""Authentication routes — register, login, refresh, and get current user.

These endpoints handle:
- Creating new user accounts
- Logging in (returns a JWT token)
- Refreshing an expiring token (get a new one without re-entering password)
- Getting the currently logged-in user's profile
"""

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import hash_password, verify_password, create_access_token, get_current_user
from apps.api.database import get_db
from apps.api.exceptions import ComioException, UnauthorizedException
from apps.api.models.user import User
from apps.api.repositories import user_repo
from apps.api.schemas.user import UserCreate, UserResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Helper ────────────────────────────────────────────

def _user_to_response(user: User) -> UserResponse:
    """Convert a User model to a UserResponse schema.

    Avoids repeating the same field mapping in every route.
    """
    return UserResponse(
        id=user.id,
        created_at=user.created_at,
        updated_at=user.updated_at,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        github_username=user.github_username,
        avatar_url=user.avatar_url,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account.

    1. Validate the input (Pydantic does this automatically)
    2. Check if email is already taken
    3. Hash the password (NEVER store plain text)
    4. Create the user in the database
    5. Return a JWT token so they're immediately logged in
    """
    # Check if email already exists
    existing_user = await user_repo.get_by_email(db, body.email)
    if existing_user:
        raise ComioException(
            message="An account with this email already exists",
            status_code=409,  # 409 Conflict
        )

    # Create the user with a hashed password
    user = await user_repo.create(
        db,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )

    # Generate a JWT token so they're logged in immediately
    access_token, expires_in = create_access_token(user.id)

    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=_user_to_response(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Log in with email and password.

    Uses OAuth2PasswordRequestForm which expects:
    - username (we use email here)
    - password

    This format is required for the Swagger UI "Authorize" button to work.
    It sends form data, not JSON.
    """
    # Look up the user by email (form_data.username contains the email)
    user = await user_repo.get_by_email(db, form_data.username)
    if not user or not user.hashed_password:
        raise UnauthorizedException("Invalid email or password")

    # Verify the password against the stored hash
    if not verify_password(form_data.password, user.hashed_password):
        raise UnauthorizedException("Invalid email or password")

    # Check account is active
    if not user.is_active:
        raise UnauthorizedException("Account is deactivated")

    # Generate JWT token
    access_token, expires_in = create_access_token(user.id)

    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=_user_to_response(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(current_user: User = Depends(get_current_user)):
    """Get a fresh JWT token using your current (still valid) token.

    How the frontend uses this:
    1. User logs in → gets token (expires in 60 min)
    2. After ~55 min, frontend calls POST /auth/refresh
       with the old token in the Authorization header
    3. Server verifies the old token is still valid
    4. Server issues a NEW token (fresh 60 min expiry)
    5. Frontend swaps old token for new one — user stays logged in

    If the old token has already expired, this returns 401
    and the user must log in again.
    """
    access_token, expires_in = create_access_token(current_user.id)

    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=_user_to_response(current_user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the currently logged-in user's profile.

    This is a PROTECTED route — requires a valid JWT token.
    Notice how simple it is: just add Depends(get_current_user).
    All the token extraction and validation happens automatically.
    """
    return _user_to_response(current_user)