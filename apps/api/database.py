from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from apps.api.config import settings

# The engine manages the connection pool to the database.
# A "pool" keeps multiple connections open and reuses them,
# so we don't have to reconnect for every single request (slow).
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  # When True, prints all SQL queries (useful for debugging)
    pool_size=20,          # Keep 20 connections open
    max_overflow=10,       # Allow up to 10 extra connections during spikes
)

# Session factory — creates new database sessions.
# expire_on_commit=False means objects stay usable after commit
# (otherwise accessing object.name after commit would fail).
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all database models.

    Every model inherits from this. SQLAlchemy uses this to track
    all your models and generate the correct SQL for table creation.
    """
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a database session per request.

    Usage in FastAPI:
        @router.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...

    The session is automatically closed when the request finishes,
    even if an error occurs (thanks to the 'finally' block).
    """
    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()