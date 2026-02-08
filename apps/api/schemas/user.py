"""User schemas for request validation and response serialization."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from apps.api.schemas.base import BaseResponse


# ── Request Schemas ────────────────────────────────────

class UserCreate(BaseModel):
    """Data required to register a new user."""
    email: EmailStr                              # Pydantic validates this is a real email format
    password: str = Field(min_length=8)          # Minimum 8 characters
    full_name: str = Field(min_length=1, max_length=255)


class UserLogin(BaseModel):
    """Data required to log in."""
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """Fields that can be updated on a user profile. All optional."""
    full_name: str | None = None
    avatar_url: str | None = None


# ── Response Schemas ───────────────────────────────────

class UserResponse(BaseResponse):
    """User data returned by the API. Never includes password or tokens."""
    email: str
    full_name: str
    role: str
    is_active: bool
    github_username: str | None = None
    avatar_url: str | None = None


class TokenResponse(BaseModel):
    """JWT token returned after login."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int       # Seconds until expiry
    user: UserResponse    # Include user data with the token
