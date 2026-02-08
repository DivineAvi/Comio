"""JWT token creation and verification.

How JWT auth works:
1. User logs in with email + password
2. Server verifies credentials, creates a JWT token
3. Server sends token back to the user
4. User includes token in every request: "Authorization: Bearer eyJ..."
5. Server decodes the token to know WHO is making the request

The token contains the user's ID (encoded, not encrypted — anyone can
read it, but they can't MODIFY it without the secret key).
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt

from apps.api.config import settings


def create_access_token(user_id: UUID) -> tuple[str, int]:
    """Create a JWT token for a user.

    Args:
        user_id: The user's UUID from the database

    Returns:
        Tuple of (token_string, expires_in_seconds)

    The token payload looks like:
        {
            "sub": "550e8400-e29b-41d4-a716-446655440000",  # user ID
            "exp": 1700000000,                                # expiry timestamp
            "iat": 1699996400,                                # issued at
        }
    """
    expires_in = settings.jwt_expire_minutes * 60  # Convert minutes to seconds
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)

    payload = {
        "sub": str(user_id),     # Subject — who this token belongs to
        "exp": expire_at,        # Expiry — when this token becomes invalid
        "iat": datetime.now(timezone.utc),  # Issued At — when this token was created
    }

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> UUID | None:
    """Decode a JWT token and extract the user ID.

    Args:
        token: The JWT string from the Authorization header

    Returns:
        The user's UUID if valid, None if token is invalid/expired

    This is called on EVERY authenticated request to figure out
    who is making the request.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            return None
        return UUID(user_id_str)
    except JWTError:
        # Token is invalid, expired, or tampered with
        return None