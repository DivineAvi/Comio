"""User repository with user-specific database operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.user import User
from apps.api.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self):
        super().__init__(User)

    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        """Find a user by email address. Used during login."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_github_id(self, db: AsyncSession, github_id: str) -> User | None:
        """Find a user by their GitHub ID. Used during OAuth login."""
        result = await db.execute(select(User).where(User.github_id == github_id))
        return result.scalar_one_or_none()


# Singleton instance — import and use this directly
user_repo = UserRepository()