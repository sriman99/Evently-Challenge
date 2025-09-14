"""
Database configuration and session management
"""

from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
from sqlalchemy import text
import logging
import asyncio
from contextlib import asynccontextmanager

from app.config import settings

logger = logging.getLogger(__name__)

# Create async engine
if settings.is_testing:
    # NullPool doesn't accept pool parameters
    engine: AsyncEngine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DB_ECHO,
        poolclass=NullPool,
    )
else:
    engine: AsyncEngine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DB_ECHO,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        poolclass=AsyncAdaptedQueuePool,
    )

# Create async session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Create declarative base
Base = declarative_base()


async def init_db():
    """
    Initialize database connections
    """
    try:
        # Test connection
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def close_db():
    """
    Close database connections
    """
    await engine.dispose()
    logger.info("Database connections closed")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get database session with explicit transaction management
    Each endpoint must use explicit transaction boundaries
    """
    async with async_session() as session:
        try:
            yield session
            # No auto-commit - endpoints must handle transactions explicitly
        except Exception:
            await session.rollback()
            raise
        # async with handles session.close() automatically


class DatabaseManager:
    """
    Production-ready database manager for transaction handling
    """

    def __init__(self):
        self.session_factory = async_session
        self.logger = logging.getLogger(__name__)

    async def execute_in_transaction(self, func, *args, **kwargs):
        """
        Execute function within a database transaction with proper error handling
        """
        async with self.session_factory() as session:
            async with session.begin():
                try:
                    result = await func(session, *args, **kwargs)
                    await session.commit()
                    return result
                except Exception as e:
                    await session.rollback()
                    self.logger.error(f"Transaction failed: {type(e).__name__}: {e}")
                    raise

    @asynccontextmanager
    async def transaction(self, session: AsyncSession):
        """
        Context manager for explicit transaction handling with proper resource management
        Uses SQLAlchemy's built-in begin() context manager for proper cleanup
        """
        try:
            # Use SQLAlchemy's built-in transaction context manager
            async with session.begin():
                yield session
                # Transaction auto-commits on successful exit
        except Exception as e:
            # Transaction auto-rolls back on exception
            self.logger.error(f"Transaction rolled back: {type(e).__name__}: {e}")
            raise

    @asynccontextmanager
    async def atomic_transaction(self):
        """
        Create a new session with atomic transaction
        """
        async with self.session_factory() as session:
            async with self.transaction(session) as tx_session:
                yield tx_session

    async def acquire_advisory_lock(self, session: AsyncSession, lock_id: int, timeout: int = 30) -> bool:
        """
        Acquire PostgreSQL advisory lock with timeout
        Returns True if lock acquired, False if timeout
        """
        try:
            # Use pg_try_advisory_lock with timeout simulation
            result = await session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": lock_id}
            )
            acquired = result.scalar()

            if not acquired and timeout > 0:
                # Retry with exponential backoff
                for attempt in range(timeout):
                    await asyncio.sleep(min(0.1 * (2 ** attempt), 1.0))
                    result = await session.execute(
                        text("SELECT pg_try_advisory_lock(:lock_id)"),
                        {"lock_id": lock_id}
                    )
                    acquired = result.scalar()
                    if acquired:
                        break

            if acquired:
                logger.debug(f"Advisory lock acquired: {lock_id}")
            else:
                logger.warning(f"Failed to acquire advisory lock: {lock_id}")

            return bool(acquired)
        except Exception as e:
            logger.error(f"Error acquiring advisory lock {lock_id}: {e}")
            return False

    async def release_advisory_lock(self, session: AsyncSession, lock_id: int) -> bool:
        """
        Release PostgreSQL advisory lock
        Returns True if lock was held and released
        """
        try:
            result = await session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": lock_id}
            )
            released = result.scalar()

            if released:
                logger.debug(f"Advisory lock released: {lock_id}")
            else:
                logger.warning(f"Advisory lock was not held: {lock_id}")

            return bool(released)
        except Exception as e:
            logger.error(f"Error releasing advisory lock {lock_id}: {e}")
            return False

    async def get_or_create(self, session: AsyncSession, model, defaults=None, **kwargs):
        """
        Get or create a database record
        """
        from sqlalchemy import select

        stmt = select(model).filter_by(**kwargs)
        result = await session.execute(stmt)
        instance = result.scalar_one_or_none()

        if instance:
            return instance, False

        params = {**kwargs, **(defaults or {})}
        instance = model(**params)
        session.add(instance)
        await session.flush()
        return instance, True

    def generate_lock_id(self, resource_type: str, resource_id: str) -> int:
        """
        Generate consistent integer lock ID from resource identifiers
        """
        import hashlib
        lock_string = f"{resource_type}:{resource_id}"
        # Generate 32-bit signed integer from hash
        hash_bytes = hashlib.md5(lock_string.encode()).digest()[:4]
        return int.from_bytes(hash_bytes, byteorder='big', signed=True)


# Create global database manager
db_manager = DatabaseManager()