"""Authentication package.

Exports the key auth utilities so other modules can import cleanly:
    from apps.api.auth import get_current_user, hash_password, verify_password
"""

from apps.api.auth.passwords import hash_password, verify_password
from apps.api.auth.jwt import create_access_token, decode_access_token
from apps.api.auth.dependencies import get_current_user, require_role, oauth2_scheme

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "require_role",
    "oauth2_scheme",
]