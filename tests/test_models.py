"""
Unit tests for database models
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.user import User, UserRole
from app.models.venue import Venue
from app.models.event import Event, EventStatus
from app.models.seat import Seat, SeatStatus
from app.models.booking import Booking, BookingStatus, BookingSeat
from app.models.transaction import Transaction, TransactionStatus
from app.models.waitlist import Waitlist
from app.core.security import get_password_hash


@pytest.mark.unit
@pytest.mark.asyncio
class TestUserModel:
    """Test User model"""

    async def test_create_user(self, db_session):
        """Test creating a user"""
        test_email = f"test_{uuid4().hex[:8]}@example.com"
        user = User(
            email=test_email,
            password_hash=get_password_hash("Password123!"),
            full_name="Test User",
            phone="+1234567890",
            role=UserRole.USER
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.id is not None
        assert user.email == test_email
        assert user.full_name == "Test User"
        assert user.role == UserRole.USER
        assert user.is_active is True
        assert user.created_at is not None

    async def test_user_unique_email(self, db_session):
        """Test email uniqueness constraint"""
        email = "unique@example.com"

        # Create first user
        user1 = User(
            email=email,
            password_hash="hash1",
            full_name="User 1"
        )
        db_session.add(user1)
        await db_session.commit()

        # Try to create second user with same email
        user2 = User(
            email=email,
            password_hash="hash2",
            full_name="User 2"
        )
        db_session.add(user2)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()

    async def test_user_roles(self, db_session):
        """Test different user roles"""
        roles = [UserRole.USER, UserRole.ADMIN, UserRole.ORGANIZER]

        for role in roles:
            user = User(
                email=f"{role.value}@example.com",
                password_hash="hash",
                full_name=f"{role.value} User",
                role=role
            )
            db_session.add(user)

        await db_session.commit()

        # Verify all roles were created
        for role in roles:
            result = await db_session.execute(
                db_session.query(User).filter_by(email=f"{role.value}@example.com")
            )
            user = result.scalar_one_or_none()
            assert user is not None
            assert user.role == role


@pytest.mark.unit
@pytest.mark.asyncio
class TestVenueModel:
    """Test Venue model"""

    async def test_create_venue(self, db_session):
        """Test creating a venue"""
        venue = Venue(
            name="Concert Hall",
            address="123 Music Street",
            city="New York",
            state="NY",
            country="USA",
            postal_code="10001",
            capacity=5000,
            layout_config={"sections": ["VIP", "General"]}
        )
        db_session.add(venue)
        await db_session.commit()
        await db_session.refresh(venue)

        assert venue.id is not None
        assert venue.name == "Concert Hall"
        assert venue.capacity == 5000
        assert venue.layout_config == {"sections": ["VIP", "General"]}


@pytest.mark.unit
@pytest.mark.asyncio
class TestEventModel:
    """Test Event model"""

    async def test_create_event(self, db_session, test_venue, test_admin):
        """Test creating an event"""
        event = Event(
            name="Summer Concert",
            description="Amazing summer concert",
            venue_id=test_venue.id,
            start_time=datetime.utcnow() + timedelta(days=30),
            end_time=datetime.utcnow() + timedelta(days=30, hours=3),
            capacity=1000,
            available_seats=1000,
            status=EventStatus.UPCOMING,
            created_by=test_admin.id
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        assert event.id is not None
        assert event.name == "Summer Concert"
        assert event.capacity == 1000
        assert event.available_seats == 1000
        assert event.status == EventStatus.UPCOMING

    async def test_event_status_transitions(self, db_session, test_venue, test_admin):
        """Test event status transitions"""
        event = Event(
            name="Test Event",
            venue_id=test_venue.id,
            start_time=datetime.utcnow() + timedelta(hours=1),
            end_time=datetime.utcnow() + timedelta(hours=4),
            capacity=100,
            available_seats=100,
            status=EventStatus.UPCOMING,
            created_by=test_admin.id
        )
        db_session.add(event)
        await db_session.commit()

        # Test status changes
        statuses = [EventStatus.ONGOING, EventStatus.COMPLETED, EventStatus.CANCELLED]
        for status in statuses:
            event.status = status
            await db_session.commit()
            await db_session.refresh(event)
            assert event.status == status


@pytest.mark.unit
@pytest.mark.asyncio
class TestSeatModel:
    """Test Seat model"""

    async def test_create_seat(self, db_session, test_event):
        """Test creating a seat"""
        seat = Seat(
            event_id=test_event.id,
            section="VIP",
            row="A",
            seat_number="1",
            price_tier="VIP",
            price=Decimal("500.00"),
            status=SeatStatus.AVAILABLE
        )
        db_session.add(seat)
        await db_session.commit()
        await db_session.refresh(seat)

        assert seat.id is not None
        assert seat.section == "VIP"
        assert seat.price == Decimal("500.00")
        assert seat.status == SeatStatus.AVAILABLE
        assert seat.version == 1  # Optimistic locking version (SQLAlchemy auto-increments)

    async def test_seat_unique_constraint(self, db_session, test_event):
        """Test seat uniqueness constraint"""
        # Create first seat
        seat1 = Seat(
            event_id=test_event.id,
            section="A",
            row="1",
            seat_number="1",
            price=Decimal("100.00")
        )
        db_session.add(seat1)
        await db_session.commit()

        # Try to create duplicate seat
        seat2 = Seat(
            event_id=test_event.id,
            section="A",
            row="1",
            seat_number="1",
            price=Decimal("100.00")
        )
        db_session.add(seat2)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()

    async def test_seat_optimistic_locking(self, db_session, test_event):
        """Test optimistic locking with version field"""
        seat = Seat(
            event_id=test_event.id,
            section="A",
            row="1",
            seat_number="1",
            price=Decimal("100.00")
        )
        db_session.add(seat)
        await db_session.commit()
        await db_session.refresh(seat)

        initial_version = seat.version
        assert initial_version == 0

        # Update seat (SQLAlchemy auto-increments version)
        seat.status = SeatStatus.BOOKED
        await db_session.commit()
        await db_session.refresh(seat)

        assert seat.version == initial_version + 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestBookingModel:
    """Test Booking model"""

    async def test_create_booking(self, db_session, test_user, test_event):
        """Test creating a booking"""
        booking = Booking(
            user_id=test_user.id,
            event_id=test_event.id,
            booking_code="BOOK123456",
            status=BookingStatus.PENDING,
            total_amount=Decimal("1000.00"),
            expires_at=datetime.utcnow() + timedelta(minutes=5)
        )
        db_session.add(booking)
        await db_session.commit()
        await db_session.refresh(booking)

        assert booking.id is not None
        assert booking.booking_code == "BOOK123456"
        assert booking.status == BookingStatus.PENDING
        assert booking.total_amount == Decimal("1000.00")

    async def test_booking_status_transitions(self, db_session, test_user, test_event):
        """Test booking status transitions"""
        booking = Booking(
            user_id=test_user.id,
            event_id=test_event.id,
            booking_code="BOOK789012",
            status=BookingStatus.PENDING,
            total_amount=Decimal("500.00")
        )
        db_session.add(booking)
        await db_session.commit()

        # Test status transitions
        booking.status = BookingStatus.CONFIRMED
        booking.confirmed_at = datetime.utcnow()
        await db_session.commit()
        assert booking.status == BookingStatus.CONFIRMED
        assert booking.confirmed_at is not None

        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = datetime.utcnow()
        await db_session.commit()
        assert booking.status == BookingStatus.CANCELLED
        assert booking.cancelled_at is not None

    async def test_booking_seat_relationship(self, db_session, test_booking, test_seats):
        """Test booking-seat relationship"""
        # Add seats to booking
        for seat in test_seats[:2]:
            booking_seat = BookingSeat(
                booking_id=test_booking.id,
                seat_id=seat.id,
                price=seat.price
            )
            db_session.add(booking_seat)

        await db_session.commit()

        # Query booking seats
        from sqlalchemy import select
        stmt = select(BookingSeat).filter_by(booking_id=test_booking.id)
        result = await db_session.execute(stmt)
        booking_seats = result.scalars().all()

        assert len(booking_seats) == 2


@pytest.mark.unit
@pytest.mark.asyncio
class TestTransactionModel:
    """Test Transaction model"""

    async def test_create_transaction(self, db_session, test_booking):
        """Test creating a transaction"""
        transaction = Transaction(
            booking_id=test_booking.id,
            amount=Decimal("1000.00"),
            status=TransactionStatus.PENDING,
            payment_method="credit_card",
            gateway_reference="stripe_ch_123456"
        )
        db_session.add(transaction)
        await db_session.commit()
        await db_session.refresh(transaction)

        assert transaction.id is not None
        assert transaction.amount == Decimal("1000.00")
        assert transaction.status == TransactionStatus.PENDING
        assert transaction.gateway_reference == "stripe_ch_123456"


@pytest.mark.unit
@pytest.mark.asyncio
class TestWaitlistModel:
    """Test Waitlist model"""

    async def test_create_waitlist_entry(self, db_session, test_user, test_event):
        """Test creating a waitlist entry"""
        waitlist = Waitlist(
            user_id=test_user.id,
            event_id=test_event.id,
            position=1
        )
        db_session.add(waitlist)
        await db_session.commit()
        await db_session.refresh(waitlist)

        assert waitlist.id is not None
        assert waitlist.position == 1
        assert waitlist.notified_at is None

    async def test_waitlist_unique_constraint(self, db_session, test_user, test_event):
        """Test user can only be on waitlist once per event"""
        # Create first entry
        waitlist1 = Waitlist(
            user_id=test_user.id,
            event_id=test_event.id,
            position=1
        )
        db_session.add(waitlist1)
        await db_session.commit()

        # Try to create duplicate entry
        waitlist2 = Waitlist(
            user_id=test_user.id,
            event_id=test_event.id,
            position=2
        )
        db_session.add(waitlist2)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.commit()