"""
Database Seeding Script for Evently
Creates sample data for testing the application
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
import random

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.config import settings
from app.core.security import get_password_hash
from app.models.base import Base
from app.models.user import User, UserRole
from app.models.venue import Venue
from app.models.event import Event, EventStatus
from app.models.seat import Seat, SeatStatus
from app.models.booking import Booking, BookingStatus, BookingSeat


# Database configuration
engine = create_async_engine(settings.DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables():
    """Create all database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] Database tables created")


async def create_users(session: AsyncSession):
    """Create sample users"""
    users = [
        {
            "email": "admin@evently.com",
            "password": "AdminPass123!",
            "full_name": "Admin User",
            "phone": "+1234567890",
            "role": UserRole.ADMIN
        },
        {
            "email": "organizer@evently.com",
            "password": "OrgPass123!",
            "full_name": "Event Organizer",
            "phone": "+1234567891",
            "role": UserRole.ORGANIZER
        },
        {
            "email": "john.doe@example.com",
            "password": "UserPass123!",
            "full_name": "John Doe",
            "phone": "+1234567892",
            "role": UserRole.USER
        },
        {
            "email": "jane.smith@example.com",
            "password": "UserPass123!",
            "full_name": "Jane Smith",
            "phone": "+1234567893",
            "role": UserRole.USER
        },
        {
            "email": "test@example.com",
            "password": "TestPass123!",
            "full_name": "Test User",
            "phone": "+1234567894",
            "role": UserRole.USER
        }
    ]

    created_users = []
    for user_data in users:
        user = User(
            email=user_data["email"],
            password_hash=get_password_hash(user_data["password"]),
            full_name=user_data["full_name"],
            phone=user_data["phone"],
            role=user_data["role"],
            is_active=True
        )
        session.add(user)
        created_users.append(user)

    await session.flush()
    print(f"[OK] Created {len(created_users)} users")
    return created_users


async def create_venues(session: AsyncSession):
    """Create sample venues"""
    venues = [
        {
            "name": "Madison Square Garden",
            "address": "4 Pennsylvania Plaza",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
            "country": "USA",
            "capacity": 20000
        },
        {
            "name": "Central Park Amphitheater",
            "address": "Central Park West",
            "city": "New York",
            "state": "NY",
            "postal_code": "10024",
            "country": "USA",
            "capacity": 5000
        },
        {
            "name": "Broadway Theatre",
            "address": "1681 Broadway",
            "city": "New York",
            "state": "NY",
            "postal_code": "10019",
            "country": "USA",
            "capacity": 1761
        },
        {
            "name": "Blue Note Jazz Club",
            "address": "131 W 3rd St",
            "city": "New York",
            "state": "NY",
            "postal_code": "10012",
            "country": "USA",
            "capacity": 300
        },
        {
            "name": "Barclays Center",
            "address": "620 Atlantic Avenue",
            "city": "Brooklyn",
            "state": "NY",
            "postal_code": "11217",
            "country": "USA",
            "capacity": 17732
        }
    ]

    created_venues = []
    for venue_data in venues:
        venue = Venue(**venue_data)
        session.add(venue)
        created_venues.append(venue)

    await session.flush()
    print(f"[OK] Created {len(created_venues)} venues")
    return created_venues


async def create_events(session: AsyncSession, venues, organizer):
    """Create sample events"""
    events_data = [
        {
            "name": "Summer Music Festival 2024",
            "description": "A 3-day music festival featuring top artists from around the world",
            "venue": venues[1],  # Central Park Amphitheater
            "start_time": datetime.utcnow() + timedelta(days=30),
            "duration_hours": 72,
            "capacity": 5000,
            "status": EventStatus.UPCOMING
        },
        {
            "name": "NBA Finals Game 7",
            "description": "The decisive game of the NBA Finals - Lakers vs Celtics",
            "venue": venues[0],  # Madison Square Garden
            "start_time": datetime.utcnow() + timedelta(days=15),
            "duration_hours": 3,
            "capacity": 20000,
            "status": EventStatus.UPCOMING
        },
        {
            "name": "Hamilton - Broadway Musical",
            "description": "The award-winning musical about Alexander Hamilton",
            "venue": venues[2],  # Broadway Theatre
            "start_time": datetime.utcnow() + timedelta(days=7),
            "duration_hours": 3,
            "capacity": 1761,
            "status": EventStatus.UPCOMING
        },
        {
            "name": "Jazz Night with John Coltrane Tribute",
            "description": "An evening celebrating the legacy of John Coltrane",
            "venue": venues[3],  # Blue Note Jazz Club
            "start_time": datetime.utcnow() + timedelta(days=3),
            "duration_hours": 4,
            "capacity": 300,
            "status": EventStatus.UPCOMING
        },
        {
            "name": "Drake World Tour 2024",
            "description": "Drake brings his latest album to life on stage",
            "venue": venues[4],  # Barclays Center
            "start_time": datetime.utcnow() + timedelta(days=45),
            "duration_hours": 3,
            "capacity": 17732,
            "status": EventStatus.UPCOMING
        },
        {
            "name": "Tech Conference 2024",
            "description": "Annual technology conference featuring industry leaders",
            "venue": venues[0],  # Madison Square Garden
            "start_time": datetime.utcnow() + timedelta(days=60),
            "duration_hours": 16,
            "capacity": 10000,
            "status": EventStatus.UPCOMING
        },
        {
            "name": "Stand-up Comedy Night",
            "description": "Featuring the best comedians from NYC",
            "venue": venues[3],  # Blue Note Jazz Club
            "start_time": datetime.utcnow() + timedelta(days=10),
            "duration_hours": 2,
            "capacity": 300,
            "status": EventStatus.UPCOMING
        },
        {
            "name": "Classical Music Concert",
            "description": "New York Philharmonic performs Beethoven's 9th Symphony",
            "venue": venues[2],  # Broadway Theatre
            "start_time": datetime.utcnow() + timedelta(days=20),
            "duration_hours": 2,
            "capacity": 1761,
            "status": EventStatus.UPCOMING
        },
        {
            "name": "Food & Wine Festival",
            "description": "Culinary delights from top chefs and wineries",
            "venue": venues[1],  # Central Park Amphitheater
            "start_time": datetime.utcnow() + timedelta(days=40),
            "duration_hours": 48,
            "capacity": 3000,
            "status": EventStatus.UPCOMING
        },
        {
            "name": "Boxing Championship",
            "description": "World Heavyweight Championship bout",
            "venue": venues[0],  # Madison Square Garden
            "start_time": datetime.utcnow() - timedelta(days=5),
            "duration_hours": 4,
            "capacity": 20000,
            "status": EventStatus.COMPLETED
        }
    ]

    created_events = []
    for event_data in events_data:
        venue = event_data.pop("venue")
        duration = event_data.pop("duration_hours")

        event = Event(
            **event_data,
            venue_id=venue.id,
            end_time=event_data["start_time"] + timedelta(hours=duration),
            available_seats=event_data["capacity"],
            created_by=organizer.id
        )
        session.add(event)
        created_events.append(event)

    await session.flush()
    print(f"[OK] Created {len(created_events)} events")
    return created_events


async def create_seats(session: AsyncSession, events):
    """Create seats for each event"""
    total_seats = 0

    for event in events:
        # Different seat configuration based on venue size
        if event.capacity <= 500:
            sections = ["A", "B"]
            rows_per_section = 10
            seats_per_row = event.capacity // (len(sections) * rows_per_section)
        elif event.capacity <= 2000:
            sections = ["A", "B", "C"]
            rows_per_section = 15
            seats_per_row = event.capacity // (len(sections) * rows_per_section)
        else:
            sections = ["A", "B", "C", "D", "E"]
            rows_per_section = 20
            seats_per_row = event.capacity // (len(sections) * rows_per_section)

        base_price = random.choice([50, 75, 100, 150, 200])

        for section in sections:
            for row in range(1, min(rows_per_section + 1, 21)):
                for seat_num in range(1, min(seats_per_row + 1, 31)):
                    # Price varies by section
                    price_multiplier = 1.0 + (ord('E') - ord(section)) * 0.3

                    seat = Seat(
                        event_id=event.id,
                        section=section,
                        row=str(row),
                        seat_number=str(seat_num),
                        price=Decimal(base_price * price_multiplier),
                        status=SeatStatus.AVAILABLE
                    )
                    session.add(seat)
                    total_seats += 1

    await session.flush()
    print(f"[OK] Created {total_seats} seats across all events")


async def create_sample_bookings(session: AsyncSession, users, events):
    """Create some sample bookings"""
    bookings_created = 0

    # Get some regular users (not admin/organizer)
    regular_users = [u for u in users if u.role == UserRole.USER]

    for event in events[:5]:  # Create bookings for first 5 events
        # Get available seats for this event
        seats_result = await session.execute(
            select(Seat).where(
                Seat.event_id == event.id,
                Seat.status == SeatStatus.AVAILABLE
            ).limit(10)
        )
        available_seats = seats_result.scalars().all()

        if available_seats:
            # Create 2-3 bookings per event
            for i in range(min(3, len(regular_users))):
                user = regular_users[i]
                seats_to_book = available_seats[i*2:(i*2)+2]  # Book 2 seats

                if seats_to_book:
                    booking = Booking(
                        user_id=user.id,
                        event_id=event.id,
                        booking_code=f"EVT{uuid.uuid4().hex[:8].upper()}",
                        status=BookingStatus.CONFIRMED,
                        total_amount=sum(seat.price for seat in seats_to_book),
                        confirmed_at=datetime.utcnow()
                    )
                    session.add(booking)
                    await session.flush()

                    # Create booking seats
                    for seat in seats_to_book:
                        booking_seat = BookingSeat(
                            booking_id=booking.id,
                            seat_id=seat.id,
                            price=seat.price
                        )
                        session.add(booking_seat)

                        # Mark seat as booked
                        seat.status = SeatStatus.BOOKED

                    # Update event available seats
                    event.available_seats -= len(seats_to_book)
                    bookings_created += 1

    await session.flush()
    print(f"[OK] Created {bookings_created} sample bookings")


async def seed_database():
    """Main seeding function"""
    print("\n>>> Starting database seeding...")

    # Create tables
    await create_tables()

    # Create session
    async with AsyncSessionLocal() as session:
        try:
            # Create users
            users = await create_users(session)

            # Get admin and organizer
            admin = next(u for u in users if u.role == UserRole.ADMIN)
            organizer = next(u for u in users if u.role == UserRole.ORGANIZER)

            # Create venues
            venues = await create_venues(session)

            # Create events
            events = await create_events(session, venues, organizer)

            # Create seats
            await create_seats(session, events)

            # Create sample bookings
            await create_sample_bookings(session, users, events)

            # Commit all changes
            await session.commit()

            print("\n[OK] Database seeding completed successfully!")
            print("\n>> Test Accounts:")
            print("  Admin: admin@evently.com / AdminPass123!")
            print("  Organizer: organizer@evently.com / OrgPass123!")
            print("  User: john.doe@example.com / UserPass123!")
            print("  User: jane.smith@example.com / UserPass123!")
            print("  User: test@example.com / TestPass123!")

        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] Error during seeding: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(seed_database())