"""
Test configuration and fixtures
Based on FastAPI + SQLAlchemy async + pytest best practices
"""

import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from datetime import datetime, timedelta
from uuid import uuid4
import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
import redis.asyncio as redis
from httpx import AsyncClient, ASGITransport

# Set test environment
os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:sriman@localhost:5432/evently"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"

# Import all models BEFORE creating fixtures (critical for create_all to work)
from app.core.database import Base
from app.models.user import User, UserRole
from app.models.venue import Venue
from app.models.event import Event, EventStatus
from app.models.seat import Seat, SeatStatus
from app.models.booking import Booking, BookingStatus, BookingSeat
from app.models.transaction import Transaction
from app.models.waitlist import Waitlist
from app.models.notification import Notification
from app.models.payment import Payment
from app.models.analytics import Analytics
from app.config import settings

# Import security functions (not the manager directly)
from app.core.security import create_access_token


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """Create async database engine for tests"""
    # Use existing database but with test-specific configuration
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=StaticPool,  # Better for testing than NullPool
        connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    )

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_db) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for tests"""
    async_session_maker = async_sessionmaker(
        test_db,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            # Ensure clean rollback if any transaction is active
            if session.in_transaction():
                await session.rollback()


@pytest_asyncio.fixture
async def client(db_session, redis_client):
    """Create test client with dependency override"""
    from app.main import app
    from app.core.database import get_session
    from app.core.redis import get_redis

    # Create a proper override function that returns the same session
    def override_get_session():
        yield db_session

    # Create a proper override function that returns the test redis client
    def override_get_redis():
        return redis_client

    # Override the dependencies
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_redis] = override_get_redis

    try:
        # Use raise_app_exceptions=False to prevent anyio.WouldBlock errors
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
    finally:
        # Clean up override
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def redis_client():
    """Create Redis client for tests"""
    client = await redis.from_url(
        settings.REDIS_URL,
        decode_responses=True
    )

    # Clear test database
    await client.flushdb()
    yield client

    # Cleanup
    await client.flushdb()
    await client.close()


# User fixtures
@pytest.fixture
def sample_user_data():
    """Sample user data"""
    return {
        "email": f"test_{uuid4().hex[:8]}@example.com",
        "password": "TestPass123!",
        "full_name": "Test User",
        "phone": "+1234567890"
    }


@pytest.fixture
def admin_user_data():
    """Admin user data"""
    return {
        "email": f"admin_{uuid4().hex[:8]}@example.com",
        "password": "AdminPass123!",
        "full_name": "Admin User",
        "phone": "+1234567890",
        "role": "admin"
    }


@pytest_asyncio.fixture
async def test_user(db_session, sample_user_data):
    """Create test user"""
    from app.core.security import get_password_hash

    user = User(
        email=sample_user_data["email"],
        password_hash=get_password_hash(sample_user_data["password"]),
        full_name=sample_user_data["full_name"],
        phone=sample_user_data["phone"],
        role=UserRole.USER,
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db_session, admin_user_data):
    """Create test admin user"""
    from app.core.security import get_password_hash

    admin = User(
        email=admin_user_data["email"],
        password_hash=get_password_hash(admin_user_data["password"]),
        full_name=admin_user_data["full_name"],
        phone=admin_user_data["phone"],
        role=UserRole.ADMIN,
        is_active=True
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def test_venue(db_session):
    """Create test venue"""
    venue = Venue(
        name="Test Arena",
        address="123 Test Street",
        city="Test City",
        state="TS",
        country="Test Country",
        postal_code="12345",
        capacity=1000
    )
    db_session.add(venue)
    await db_session.commit()
    await db_session.refresh(venue)
    return venue


@pytest_asyncio.fixture
async def test_event(db_session, test_venue, test_admin):
    """Create test event"""
    event = Event(
        name="Test Concert",
        description="Test concert description",
        venue_id=test_venue.id,
        start_time=datetime.utcnow() + timedelta(days=30),
        end_time=datetime.utcnow() + timedelta(days=30, hours=3),
        capacity=1000,
        available_seats=1000,  # Set initial available seats
        status=EventStatus.UPCOMING,
        created_by=test_admin.id
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


@pytest_asyncio.fixture
async def test_seats(db_session, test_event):
    """Create test seats"""
    seats = []
    sections = ["VIP", "Premium", "General"]
    prices = [500.00, 200.00, 50.00]

    for section_idx, section in enumerate(sections):
        for row in ["A", "B", "C"]:
            for seat_num in range(1, 11):
                seat = Seat(
                    event_id=test_event.id,
                    section=section,
                    row=row,
                    seat_number=str(seat_num),
                    price_tier=section,
                    price=prices[section_idx],
                    status=SeatStatus.AVAILABLE
                )
                seats.append(seat)
                db_session.add(seat)

    await db_session.commit()
    for seat in seats:
        await db_session.refresh(seat)

    return seats


@pytest_asyncio.fixture
async def test_booking(db_session, test_user, test_event, test_seats):
    """Create test booking"""
    import random
    import string

    # Create booking
    booking_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    selected_seats = test_seats[:2]  # Book first 2 seats

    booking = Booking(
        user_id=test_user.id,
        event_id=test_event.id,
        booking_code=booking_code,
        status=BookingStatus.CONFIRMED,
        total_amount=sum(seat.price for seat in selected_seats),
        confirmed_at=datetime.utcnow()
    )
    db_session.add(booking)
    await db_session.flush()

    # Add booking seats
    for seat in selected_seats:
        booking_seat = BookingSeat(
            booking_id=booking.id,
            seat_id=seat.id,
            price=seat.price
        )
        db_session.add(booking_seat)

    await db_session.commit()
    await db_session.refresh(booking)
    return booking


@pytest_asyncio.fixture
async def auth_headers_user(test_user):
    """Generate auth headers for test user"""
    token = create_access_token(
        data={"sub": str(test_user.id), "email": test_user.email, "role": test_user.role.value}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def auth_headers_admin(test_admin):
    """Generate auth headers for admin user"""
    token = create_access_token(
        data={"sub": str(test_admin.id), "email": test_admin.email, "role": test_admin.role.value}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def multiple_events(db_session, test_venue, test_admin):
    """Create multiple events for testing"""
    events = []
    event_data = [
        {"name": "Jazz Night", "days_offset": 7},
        {"name": "Rock Concert", "days_offset": 14},
        {"name": "Classical Evening", "days_offset": 21},
        {"name": "Pop Festival", "days_offset": 28},
        {"name": "Electronic Music", "days_offset": 35}
    ]

    for data in event_data:
        event = Event(
            name=data["name"],
            description=f"Description for {data['name']}",
            venue_id=test_venue.id,
            start_time=datetime.utcnow() + timedelta(days=data["days_offset"]),
            end_time=datetime.utcnow() + timedelta(days=data["days_offset"], hours=3),
            capacity=1000,
            available_seats=1000,  # Set initial available seats
            status=EventStatus.UPCOMING,
            created_by=test_admin.id
        )
        events.append(event)
        db_session.add(event)

    await db_session.commit()
    for event in events:
        await db_session.refresh(event)

    return events


async def create_multiple_users(db_session, count: int):
    """Helper function to create multiple users"""
    from app.core.security import get_password_hash

    users = []
    for i in range(count):
        user = User(
            email=f"testuser{i}_{uuid4().hex[:8]}@example.com",
            password_hash=get_password_hash("TestPass123!"),
            full_name=f"Test User {i}",
            phone=f"+1234567{i:03d}",
            role=UserRole.USER,
            is_active=True
        )
        users.append(user)
        db_session.add(user)

    await db_session.commit()
    for user in users:
        await db_session.refresh(user)

    return users


@pytest_asyncio.fixture
async def test_redis():
    """Create Redis client for tests"""
    client = await redis.from_url(
        "redis://localhost:6379/1",
        decode_responses=True
    )

    # Clear test database
    await client.flushdb()
    yield client

    # Cleanup
    await client.flushdb()
    await client.close()