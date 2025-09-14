#!/usr/bin/env python3
"""
Seed database with demo data for evaluators
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from uuid import uuid4
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings
from app.core.database import async_session, init_db
from app.models.user import User, UserRole
from app.models.venue import Venue
from app.models.event import Event, EventStatus
from app.models.seat import Seat, SeatStatus
from app.core.security import get_password_hash


async def create_demo_users():
    """Create demo users for evaluation"""
    async with async_session() as session:
        # Admin user
        admin_user = User(
            id=uuid4(),
            email="admin@evently.com",
            full_name="Admin User",
            phone="+1234567890",
            hashed_password=get_password_hash("Admin123!"),
            role=UserRole.ADMIN,
            is_active=True
        )

        # Regular demo user
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
        await session.commit()
        print("✅ Created demo users")
        return admin_user.id, demo_user.id


async def create_demo_venues():
    """Create demo venues"""
    async with async_session() as session:
        venues = [
            Venue(
                id=uuid4(),
                name="Grand Theater",
                address="123 Main St, New York, NY 10001",
                city="New York",
                state="NY",
                country="USA",
                capacity=500,
                description="A beautiful historic theater in the heart of Manhattan"
            ),
            Venue(
                id=uuid4(),
                name="Convention Center",
                address="456 Convention Ave, San Francisco, CA 94102",
                city="San Francisco",
                state="CA",
                country="USA",
                capacity=1000,
                description="Modern convention center perfect for large events"
            )
        ]

        for venue in venues:
            session.add(venue)
        await session.commit()
        print("✅ Created demo venues")
        return [v.id for v in venues]


async def create_demo_events(venue_ids):
    """Create demo events"""
    async with async_session() as session:
        events = [
            Event(
                id=uuid4(),
                name="Broadway Musical Night",
                description="An evening of classic Broadway hits performed by renowned artists",
                venue_id=venue_ids[0],
                start_time=datetime.now() + timedelta(days=30),
                end_time=datetime.now() + timedelta(days=30, hours=3),
                capacity=500,
                available_seats=500,
                status=EventStatus.UPCOMING,
                min_price=Decimal("50.00"),
                max_price=Decimal("200.00")
            ),
            Event(
                id=uuid4(),
                name="Tech Conference 2025",
                description="Join industry leaders for the latest in technology and innovation",
                venue_id=venue_ids[1],
                start_time=datetime.now() + timedelta(days=45),
                end_time=datetime.now() + timedelta(days=47),
                capacity=1000,
                available_seats=1000,
                status=EventStatus.UPCOMING,
                min_price=Decimal("100.00"),
                max_price=Decimal("500.00")
            ),
            Event(
                id=uuid4(),
                name="Jazz Festival",
                description="A celebration of jazz music with local and international artists",
                venue_id=venue_ids[0],
                start_time=datetime.now() + timedelta(days=60),
                end_time=datetime.now() + timedelta(days=60, hours=6),
                capacity=500,
                available_seats=450,  # Some seats already "booked"
                status=EventStatus.UPCOMING,
                min_price=Decimal("75.00"),
                max_price=Decimal("250.00")
            )
        ]

        for event in events:
            session.add(event)
        await session.commit()
        print("✅ Created demo events")
        return [e.id for e in events]


async def create_demo_seats(event_ids):
    """Create demo seats for events"""
    async with async_session() as session:
        sections = ["Orchestra", "Mezzanine", "Balcony"]

        for event_id in event_ids:
            seat_count = 0
            for section in sections:
                for row in ["A", "B", "C", "D", "E"]:
                    for seat_num in range(1, 21):  # 20 seats per row
                        price = Decimal("50.00")
                        if section == "Orchestra":
                            price = Decimal("200.00")
                        elif section == "Mezzanine":
                            price = Decimal("150.00")
                        else:
                            price = Decimal("100.00")

                        # Make some seats unavailable for the Jazz Festival
                        status = SeatStatus.AVAILABLE
                        if event_id == event_ids[2] and seat_count < 50:
                            status = SeatStatus.BOOKED

                        seat = Seat(
                            id=uuid4(),
                            event_id=event_id,
                            section=section,
                            row=row,
                            seat_number=str(seat_num),
                            price=price,
                            status=status
                        )
                        session.add(seat)
                        seat_count += 1

        await session.commit()
        print("✅ Created demo seats")


async def main():
    """Main seeding function"""
    print("🌱 Starting database seeding...")

    # Initialize database
    await init_db()

    try:
        # Create demo data
        user_ids = await create_demo_users()
        venue_ids = await create_demo_venues()
        event_ids = await create_demo_events(venue_ids)
        await create_demo_seats(event_ids)

        print("\n🎉 Database seeding completed successfully!")
        print("\n🔑 Demo Credentials:")
        print("👤 Admin: admin@evently.com / Admin123!")
        print("👤 User:  demo@evently.com / Demo123!")
        print("\n🌐 Test your API at: https://evently-challenge-production.up.railway.app/docs")

    except Exception as e:
        print(f"❌ Error seeding database: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())