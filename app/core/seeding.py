"""
Auto-seeding for production database
"""
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
from decimal import Decimal

from app.core.database import async_session
from app.models.user import User, UserRole
from app.models.venue import Venue
from app.models.event import Event, EventStatus
from app.models.seat import Seat, SeatStatus
from app.core.security import get_password_hash
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)


async def seed_if_empty():
    """Seed database only if it's empty (for production auto-seeding)"""
    async with async_session() as session:
        # Check if users exist
        result = await session.execute(select(User).limit(1))
        if result.scalar_one_or_none():
            logger.info("Database already contains data, skipping seeding")
            return

        logger.info("Empty database detected, starting auto-seeding...")

        try:
            # Create demo users
            admin_user = User(
                id=uuid4(),
                email="admin@evently.com",
                full_name="Admin User",
                phone="+1234567890",
                hashed_password=get_password_hash("Admin123!"),
                role=UserRole.ADMIN,
                is_active=True
            )

            demo_user = User(
                id=uuid4(),
                email="demo@evently.com",
                full_name="Demo User",
                phone="+1987654321",
                hashed_password=get_password_hash("Demo123!"),
                role=UserRole.USER,
                is_active=True
            )

            session.add(admin_user)
            session.add(demo_user)

            # Create demo venues
            venue1 = Venue(
                id=uuid4(),
                name="Grand Theater",
                address="123 Main St, New York, NY 10001",
                city="New York",
                state="NY",
                country="USA",
                capacity=500,
                description="A beautiful historic theater in the heart of Manhattan"
            )

            venue2 = Venue(
                id=uuid4(),
                name="Convention Center",
                address="456 Convention Ave, San Francisco, CA 94102",
                city="San Francisco",
                state="CA",
                country="USA",
                capacity=1000,
                description="Modern convention center perfect for large events"
            )

            session.add(venue1)
            session.add(venue2)

            # Create demo events
            event1 = Event(
                id=uuid4(),
                name="Broadway Musical Night",
                description="An evening of classic Broadway hits performed by renowned artists",
                venue_id=venue1.id,
                start_time=datetime.now() + timedelta(days=30),
                end_time=datetime.now() + timedelta(days=30, hours=3),
                capacity=500,
                available_seats=500,
                status=EventStatus.UPCOMING,
                min_price=Decimal("50.00"),
                max_price=Decimal("200.00")
            )

            event2 = Event(
                id=uuid4(),
                name="Tech Conference 2025",
                description="Join industry leaders for the latest in technology and innovation",
                venue_id=venue2.id,
                start_time=datetime.now() + timedelta(days=45),
                end_time=datetime.now() + timedelta(days=47),
                capacity=1000,
                available_seats=1000,
                status=EventStatus.UPCOMING,
                min_price=Decimal("100.00"),
                max_price=Decimal("500.00")
            )

            session.add(event1)
            session.add(event2)
            await session.commit()

            # Create some demo seats
            sections = ["Orchestra", "Mezzanine", "Balcony"]
            for event in [event1, event2]:
                for section in sections:
                    for row in ["A", "B", "C"]:
                        for seat_num in range(1, 11):  # 10 seats per row
                            price = Decimal("150.00")
                            if section == "Orchestra":
                                price = Decimal("200.00")
                            elif section == "Balcony":
                                price = Decimal("100.00")

                            seat = Seat(
                                id=uuid4(),
                                event_id=event.id,
                                section=section,
                                row=row,
                                seat_number=str(seat_num),
                                price=price,
                                status=SeatStatus.AVAILABLE
                            )
                            session.add(seat)

            await session.commit()
            logger.info("Auto-seeding completed successfully")

        except Exception as e:
            await session.rollback()
            logger.error(f"Auto-seeding failed: {e}")
            raise