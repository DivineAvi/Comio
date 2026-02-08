"""Password hashing utilities using bcrypt directly.

Why bcrypt?
- It's intentionally SLOW (makes brute-force attacks impractical)
- It adds random "salt" automatically (same password → different hash each time)
- It's the industry standard for password storage

NEVER store plain-text passwords. Always hash them.

Note: We use the 'bcrypt' library directly instead of 'passlib' because
passlib is unmaintained and incompatible with bcrypt >= 4.1.
"""

import bcrypt


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password.

    Input:  "MySecret123"
    Output: "$2b$12$LJ3m4ks..." (60-character hash string)

    Used during: user registration
    """
    # bcrypt works with bytes, so we encode the string to UTF-8
    password_bytes = plain_password.encode("utf-8")
    # gensalt() creates a random salt with 12 rounds (default)
    # More rounds = slower hashing = harder to brute-force
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    # Return as string for storage in the database
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check if a plain-text password matches a stored hash.

    Input:  "MySecret123", "$2b$12$LJ3m4ks..."
    Output: True or False

    Used during: user login
    """
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)