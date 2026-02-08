"""Base repository with generic CRUD operations.

Every model-specific repository inherits from this.
You get create, get, list, update, delete for free.
"""

import uuid
from typing import Generic, TypeVar, Type

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.base import BaseModel

# TypeVar lets us write one class that works for User, Project, Incident, etc.
# "ModelType" is a placeholder that gets replaced with the actual model class.
ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(Generic[ModelType]):
    """Generic repository providing CRUD operations for any model.

    Usage:
        class UserRepository(BaseRepository[User]):
            def __init__(self):
                super().__init__(User)

        user_repo = UserRepository()
        user = await user_repo.get_by_id(db, some_uuid)
    """

    def __init__(self, model: Type[ModelType]):
        self.model = model

    async def get_by_id(self, db: AsyncSession, id: uuid.UUID) -> ModelType | None:
        """Get a single record by its UUID. Returns None if not found."""
        result = await db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_all(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelType]:
        """Get a paginated list of records.

        Args:
            skip: Number of records to skip (for pagination offset)
            limit: Maximum number of records to return
        """
        result = await db.execute(
            select(self.model)
            .offset(skip)
            .limit(limit)
            .order_by(self.model.created_at.desc())  # Newest first
        )
        return list(result.scalars().all())

    async def count(self, db: AsyncSession) -> int:
        """Get total count of records."""
        result = await db.execute(select(func.count()).select_from(self.model))
        return result.scalar_one()

    async def create(self, db: AsyncSession, **kwargs) -> ModelType:
        """Create a new record.

        Usage: user = await user_repo.create(db, email="bob@test.com", full_name="Bob")
        """
        instance = self.model(**kwargs)
        db.add(instance)
        await db.commit()
        await db.refresh(instance)  # Reload from DB to get id, created_at, etc.
        return instance

    async def update(
        self, db: AsyncSession, instance: ModelType, **kwargs
    ) -> ModelType:
        """Update an existing record.

        Usage: user = await user_repo.update(db, user, full_name="Robert")
        """
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await db.commit()
        await db.refresh(instance)
        return instance

    async def delete(self, db: AsyncSession, instance: ModelType) -> None:
        """Delete a record from the database."""
        await db.delete(instance)
        await db.commit()