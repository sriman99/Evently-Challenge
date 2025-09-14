"""
Migration: Add reservation fields to seats table

This migration adds support for tracking seat reservations
"""

from sqlalchemy import text
import asyncio
from app.core.database import engine


async def upgrade():
    """Add reservation fields to seats table"""

    migration_statements = [
        """
        ALTER TABLE seats
        ADD COLUMN IF NOT EXISTS reserved_by UUID REFERENCES users(id),
        ADD COLUMN IF NOT EXISTS reserved_at TIMESTAMP
        """,
        "CREATE INDEX IF NOT EXISTS idx_seats_reserved_by ON seats(reserved_by)",
        "CREATE INDEX IF NOT EXISTS idx_seats_reserved_at ON seats(reserved_at)",
        "CREATE INDEX IF NOT EXISTS idx_seats_event_status ON seats(event_id, status)"
    ]

    async with engine.begin() as conn:
        for statement in migration_statements:
            try:
                await conn.execute(text(statement.strip()))
                print(f"Executed: {statement.strip().split()[0]} ...")
            except Exception as e:
                print(f"Warning - {e} (might already exist)")

    print("Migration completed: Added seat reservation fields")


async def downgrade():
    """Remove reservation fields from seats table"""

    rollback_sql = """
    -- Remove indexes first
    DROP INDEX IF EXISTS idx_seats_reserved_by;
    DROP INDEX IF EXISTS idx_seats_reserved_at;
    DROP INDEX IF EXISTS idx_seats_event_status;

    -- Remove columns
    ALTER TABLE seats
    DROP COLUMN IF EXISTS reserved_by,
    DROP COLUMN IF EXISTS reserved_at;
    """

    async with engine.begin() as conn:
        await conn.execute(text(rollback_sql))

    print("Rollback completed: Removed seat reservation fields")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        asyncio.run(downgrade())
    else:
        asyncio.run(upgrade())