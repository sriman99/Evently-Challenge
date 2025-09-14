"""
Migration to create saga_states table
"""

import asyncio
import asyncpg
import os
from app.config import settings
from app.models.saga_state import SagaState
from app.core.database import engine, async_session


async def create_saga_states_table():
    """Create the saga_states table if it doesn't exist"""
    try:
        # Import the model to ensure it's registered
        from app.models.saga_state import SagaState
        from app.core.database import Base

        print("Creating saga_states table...")

        # Create the table using SQLAlchemy metadata
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=[SagaState.__table__])

        print("✅ saga_states table created successfully")

    except Exception as e:
        print(f"❌ Error creating saga_states table: {e}")
        raise


async def verify_table_exists():
    """Verify that the saga_states table exists and is accessible"""
    try:
        async with async_session() as session:
            # Try to query the table
            from sqlalchemy import text
            result = await session.execute(text("SELECT COUNT(*) FROM saga_states"))
            count = result.scalar()
            print(f"✅ saga_states table verified - current record count: {count}")

    except Exception as e:
        print(f"❌ Error verifying saga_states table: {e}")
        raise


async def main():
    """Main migration function"""
    print("Starting saga_states table migration...")

    await create_saga_states_table()
    await verify_table_exists()

    print("Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())