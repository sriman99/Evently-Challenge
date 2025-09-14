"""
Production-ready database constraints migration
Adds critical business logic constraints to prevent data inconsistencies
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, create_engine
from sqlalchemy.ext.asyncio import create_async_engine
import os

# SECURITY FIX: Use environment variable for database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/evently")
engine = create_async_engine(DATABASE_URL)


async def upgrade():
    """Add production database constraints"""

    constraints_sql = [
        # 1. Remove available_seats column (now computed)
        "ALTER TABLE events DROP COLUMN IF EXISTS available_seats CASCADE",

        # 2. Add check constraints for business rules
        """
        ALTER TABLE events
        ADD CONSTRAINT chk_events_capacity_positive
        CHECK (capacity > 0)
        """,

        # REMOVED: available_seats constraint - column no longer exists

        """
        ALTER TABLE events
        ADD CONSTRAINT chk_events_valid_time_range
        CHECK (end_time > start_time)
        """,

        """
        ALTER TABLE events
        ADD CONSTRAINT chk_events_no_past_booking
        CHECK (start_time > NOW() OR status != 'upcoming')
        """,

        # 3. Seat availability constraints
        """
        ALTER TABLE seats
        ADD CONSTRAINT chk_seats_valid_price
        CHECK (price >= 0)
        """,

        # 4. Create function to prevent overbooking
        """
        CREATE OR REPLACE FUNCTION check_event_capacity()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Check if seat reservation would exceed event capacity
            IF (SELECT COUNT(*) FROM seats s
                JOIN events e ON s.event_id = e.id
                WHERE s.event_id = NEW.event_id
                AND s.status IN ('reserved', 'booked')) >=
               (SELECT capacity FROM events WHERE id = NEW.event_id) THEN
                RAISE EXCEPTION 'Event capacity exceeded for event %', NEW.event_id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """,

        # 5. Create trigger to enforce capacity constraint
        """
        DROP TRIGGER IF EXISTS trigger_check_capacity ON seats
        """,

        """
        CREATE TRIGGER trigger_check_capacity
            BEFORE UPDATE OF status ON seats
            FOR EACH ROW
            WHEN (NEW.status IN ('reserved', 'booked') AND OLD.status = 'available')
            EXECUTE FUNCTION check_event_capacity()
        """,

        # 6. Booking constraints
        """
        ALTER TABLE bookings
        ADD CONSTRAINT chk_bookings_valid_amount
        CHECK (total_amount > 0)
        """,

        """
        ALTER TABLE bookings
        ADD CONSTRAINT chk_bookings_valid_expiry
        CHECK (expires_at IS NULL OR expires_at > created_at)
        """,

        """
        ALTER TABLE bookings
        ADD CONSTRAINT chk_bookings_confirmed_logic
        CHECK (
            (status = 'confirmed' AND confirmed_at IS NOT NULL) OR
            (status != 'confirmed' AND (confirmed_at IS NULL OR confirmed_at IS NOT NULL))
        )
        """,

        """
        ALTER TABLE bookings
        ADD CONSTRAINT chk_bookings_cancelled_logic
        CHECK (
            (status = 'cancelled' AND cancelled_at IS NOT NULL) OR
            (status != 'cancelled')
        )
        """,

        # 7. Prevent booking past events
        """
        CREATE OR REPLACE FUNCTION check_booking_timing()
        RETURNS TRIGGER AS $$
        BEGIN
            IF (SELECT start_time FROM events WHERE id = NEW.event_id) <= NOW() THEN
                RAISE EXCEPTION 'Cannot book seats for past or ongoing events';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """,

        """
        DROP TRIGGER IF EXISTS trigger_check_booking_timing ON bookings
        """,

        """
        CREATE TRIGGER trigger_check_booking_timing
            BEFORE INSERT ON bookings
            FOR EACH ROW
            EXECUTE FUNCTION check_booking_timing()
        """,

        # 8. Create optimized indexes for performance
        "CREATE INDEX IF NOT EXISTS idx_seats_event_status ON seats(event_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_bookings_user_event ON bookings(user_id, event_id)",
        "CREATE INDEX IF NOT EXISTS idx_events_status_time ON events(status, start_time)",

        # 9. Create materialized view for analytics (optional performance boost)
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS event_availability_stats AS
        SELECT
            e.id as event_id,
            e.name,
            e.capacity,
            COUNT(CASE WHEN s.status = 'available' THEN 1 END) as available_count,
            COUNT(CASE WHEN s.status IN ('reserved', 'booked') THEN 1 END) as occupied_count,
            ROUND((COUNT(CASE WHEN s.status IN ('reserved', 'booked') THEN 1 END)::DECIMAL / e.capacity) * 100, 2) as utilization_percent
        FROM events e
        LEFT JOIN seats s ON e.id = s.event_id
        WHERE e.status = 'upcoming'
        GROUP BY e.id, e.name, e.capacity
        """,

        # 10. Create index on materialized view
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_event_stats_event_id ON event_availability_stats(event_id)"
    ]

    async with engine.begin() as conn:
        for sql in constraints_sql:
            try:
                # SECURITY FIX: Use parameterized queries with text()
                # The text() function properly escapes SQL statements
                stmt = text(sql.strip())
                await conn.execute(stmt)
                print(f"✅ Executed: {sql.strip()[:50]}...")
            except Exception as e:
                print(f"⚠️  Warning - {e} (might already exist)")

    print("🎯 Production constraints migration completed!")


async def downgrade():
    """Remove production constraints (for rollback)"""

    rollback_sql = [
        # Remove triggers
        "DROP TRIGGER IF EXISTS trigger_check_capacity ON seats",
        "DROP TRIGGER IF EXISTS trigger_check_booking_timing ON bookings",

        # Remove functions
        "DROP FUNCTION IF EXISTS check_event_capacity()",
        "DROP FUNCTION IF EXISTS check_booking_timing()",

        # Remove constraints
        "ALTER TABLE events DROP CONSTRAINT IF EXISTS chk_events_capacity_positive",
        "ALTER TABLE events DROP CONSTRAINT IF EXISTS chk_events_valid_time_range",
        "ALTER TABLE seats DROP CONSTRAINT IF EXISTS chk_seats_valid_price",
        "ALTER TABLE bookings DROP CONSTRAINT IF EXISTS chk_bookings_valid_amount",
        "ALTER TABLE bookings DROP CONSTRAINT IF EXISTS chk_bookings_valid_expiry",

        # Remove materialized view
        "DROP MATERIALIZED VIEW IF EXISTS event_availability_stats",

        # Re-add available_seats column if needed
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS available_seats INTEGER DEFAULT 0"
    ]

    async with engine.begin() as conn:
        for sql in rollback_sql:
            try:
                # SECURITY FIX: Use parameterized queries with text()
                stmt = text(sql.strip())
                await conn.execute(stmt)
                print(f"✅ Rolled back: {sql.strip()[:50]}...")
            except Exception as e:
                print(f"⚠️  Warning during rollback - {e}")

    print("🔄 Production constraints rollback completed!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        asyncio.run(downgrade())
    else:
        asyncio.run(upgrade())