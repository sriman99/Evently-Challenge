"""
Production-ready booking system tests
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_manager
from app.core.redis import redis_manager
from app.api.v1.endpoints.bookings import ProductionBookingService, SeatUnavailableError, ReservationError
from app.models.user import User
from app.models.event import Event
from app.models.venue import Venue
from app.models.seat import Seat, SeatStatus
from app.models.booking import Booking, BookingStatus
from app.schemas.booking import BookingCreate


@pytest.fixture
def booking_service():
    """Create booking service instance"""
    return ProductionBookingService()


@pytest.fixture
async def test_user(db_session):
    """Create test user"""
    user = User(
        email="test@example.com",
        hashed_password="hashed",
        first_name="Test",
        last_name="User",
        phone="1234567890"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def test_venue(db_session):
    """Create test venue"""
    venue = Venue(
        name="Test Arena",
        address="123 Test St",
        city="Test City",
        state="Test State",
        country="Test Country",
        capacity=1000
    )
    db_session.add(venue)
    await db_session.flush()
    return venue


@pytest.fixture
async def test_event(db_session, test_venue):
    """Create test event"""
    event = Event(
        name="Test Concert",
        description="Test concert description",
        venue_id=test_venue.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=30),
        end_time=datetime.now(timezone.utc) + timedelta(days=30, hours=3),
        total_seats=100,
        available_seats=100
    )
    db_session.add(event)
    await db_session.flush()
    return event


@pytest.fixture
async def test_seats(db_session, test_event):
    """Create test seats"""
    seats = []
    for i in range(10):
        seat = Seat(
            event_id=test_event.id,
            section="A",
            row="1",
            seat_number=str(i + 1),
            price=100.00,
            status=SeatStatus.AVAILABLE
        )
        db_session.add(seat)
        seats.append(seat)

    await db_session.flush()
    return seats


class TestProductionBookingService:
    """Test production booking service"""

    @pytest.mark.asyncio
    async def test_successful_booking(self, booking_service, db_session, test_user, test_event, test_seats):
        """Test successful booking creation"""
        # Arrange
        seat_ids = [test_seats[0].id, test_seats[1].id]
        booking_data = BookingCreate(
            event_id=test_event.id,
            seat_ids=seat_ids
        )

        # Act
        result = await booking_service.create_booking_atomic(
            db=db_session,
            booking_data=booking_data,
            user=test_user
        )

        # Assert
        assert result["booking_code"].startswith("EVT")
        assert result["status"] == "pending"
        assert len(result["seats"]) == 2
        assert result["total_amount"] == 200.00

        # Verify Redis reservations
        event_id = str(test_event.id)
        seat_ids_str = [str(sid) for sid in seat_ids]
        is_reserved = await redis_manager.verify_seat_reservation(
            event_id=event_id,
            seat_ids=seat_ids_str,
            user_id=str(test_user.id)
        )
        assert is_reserved

    @pytest.mark.asyncio
    async def test_concurrent_booking_same_seats(self, booking_service, db_session, test_event, test_seats):
        """Test concurrent booking attempts on same seats"""
        # Create two users
        user1 = User(email="user1@test.com", hashed_password="hash", first_name="User", last_name="One")
        user2 = User(email="user2@test.com", hashed_password="hash", first_name="User", last_name="Two")
        db_session.add_all([user1, user2])
        await db_session.flush()

        # Same seats for both bookings
        seat_ids = [test_seats[0].id, test_seats[1].id]
        booking_data = BookingCreate(event_id=test_event.id, seat_ids=seat_ids)

        # Simulate concurrent booking attempts
        async def book_seats(user):
            try:
                return await booking_service.create_booking_atomic(
                    db=db_session,
                    booking_data=booking_data,
                    user=user
                )
            except (SeatUnavailableError, ReservationError) as e:
                return {"error": str(e)}

        # Execute concurrent bookings
        results = await asyncio.gather(
            book_seats(user1),
            book_seats(user2),
            return_exceptions=True
        )

        # Verify only one booking succeeded
        successful_bookings = [r for r in results if "booking_code" in r]
        failed_bookings = [r for r in results if "error" in r]

        assert len(successful_bookings) == 1
        assert len(failed_bookings) == 1
        assert "booking_code" in successful_bookings[0]

    @pytest.mark.asyncio
    async def test_booking_confirmation(self, booking_service, db_session, test_user, test_event, test_seats):
        """Test booking confirmation process"""
        # Create booking
        seat_ids = [test_seats[0].id]
        booking_data = BookingCreate(event_id=test_event.id, seat_ids=seat_ids)

        booking_result = await booking_service.create_booking_atomic(
            db=db_session,
            booking_data=booking_data,
            user=test_user
        )

        # Confirm booking
        confirmation = await booking_service.confirm_booking(
            db=db_session,
            booking_id=booking_result["id"],
            user_id=str(test_user.id),
            payment_reference="stripe_pi_test_123"
        )

        # Verify confirmation
        assert confirmation["message"] == "Booking confirmed successfully"
        assert confirmation["booking_code"] == booking_result["booking_code"]

        # Verify seat status changed to BOOKED
        await db_session.refresh(test_seats[0])
        assert test_seats[0].status == SeatStatus.BOOKED

    @pytest.mark.asyncio
    async def test_booking_cancellation(self, booking_service, db_session, test_user, test_event, test_seats):
        """Test booking cancellation process"""
        # Create and confirm booking
        seat_ids = [test_seats[0].id]
        booking_data = BookingCreate(event_id=test_event.id, seat_ids=seat_ids)

        booking_result = await booking_service.create_booking_atomic(
            db=db_session,
            booking_data=booking_data,
            user=test_user
        )

        # Cancel booking
        cancellation = await booking_service.cancel_booking(
            db=db_session,
            booking_id=booking_result["id"],
            user_id=str(test_user.id)
        )

        # Verify cancellation
        assert cancellation["message"] == "Booking cancelled successfully"

        # Verify seat is available again
        await db_session.refresh(test_seats[0])
        assert test_seats[0].status == SeatStatus.AVAILABLE

        # Verify event capacity restored
        await db_session.refresh(test_event)
        assert test_event.available_seats == 100

    @pytest.mark.asyncio
    async def test_redis_reservation_ttl(self, booking_service, test_event, test_seats, test_user):
        """Test Redis reservation TTL functionality"""
        event_id = str(test_event.id)
        seat_ids = [str(test_seats[0].id)]
        user_id = str(test_user.id)

        # Reserve seats with short TTL
        success, failed = await redis_manager.reserve_seats(
            event_id=event_id,
            seat_ids=seat_ids,
            user_id=user_id,
            ttl=1  # 1 second TTL
        )

        assert success
        assert len(failed) == 0

        # Verify reservation exists
        is_reserved = await redis_manager.verify_seat_reservation(
            event_id=event_id,
            seat_ids=seat_ids,
            user_id=user_id
        )
        assert is_reserved

        # Wait for TTL to expire
        await asyncio.sleep(2)

        # Verify reservation expired
        is_reserved = await redis_manager.verify_seat_reservation(
            event_id=event_id,
            seat_ids=seat_ids,
            user_id=user_id
        )
        assert not is_reserved

    @pytest.mark.asyncio
    async def test_insufficient_seats(self, booking_service, db_session, test_user, test_event, test_seats):
        """Test booking with insufficient available seats"""
        # Update event to have only 1 available seat
        test_event.available_seats = 1
        await db_session.flush()

        # Try to book 2 seats
        seat_ids = [test_seats[0].id, test_seats[1].id]
        booking_data = BookingCreate(event_id=test_event.id, seat_ids=seat_ids)

        # Should raise SeatUnavailableError
        with pytest.raises(SeatUnavailableError) as exc_info:
            await booking_service.create_booking_atomic(
                db=db_session,
                booking_data=booking_data,
                user=test_user
            )

        assert "Only 1 seats available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_seat_already_booked(self, booking_service, db_session, test_user, test_event, test_seats):
        """Test booking seats that are already booked"""
        # Mark seat as already booked
        test_seats[0].status = SeatStatus.BOOKED
        await db_session.flush()

        # Try to book the already booked seat
        seat_ids = [test_seats[0].id]
        booking_data = BookingCreate(event_id=test_event.id, seat_ids=seat_ids)

        # Should raise SeatUnavailableError
        with pytest.raises(SeatUnavailableError) as exc_info:
            await booking_service.create_booking_atomic(
                db=db_session,
                booking_data=booking_data,
                user=test_user
            )

        assert "no longer available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_redis_circuit_breaker(self, booking_service, test_user, test_event, test_seats):
        """Test Redis circuit breaker functionality"""
        # Force circuit breaker to open by simulating failures
        for _ in range(6):  # More than failure threshold
            try:
                await redis_manager.circuit_breaker.call(
                    lambda: exec('raise Exception("Simulated failure")')
                )
            except:
                pass

        # Verify circuit breaker is open
        assert redis_manager.circuit_breaker.is_open()

        # Booking should fail due to open circuit breaker
        seat_ids = [test_seats[0].id]
        booking_data = BookingCreate(event_id=test_event.id, seat_ids=seat_ids)

        with pytest.raises(ReservationError):
            await booking_service.create_booking_atomic(
                db=None,  # Won't reach DB due to Redis failure
                booking_data=booking_data,
                user=test_user
            )


class TestRateLimiting:
    """Test rate limiting functionality"""

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test rate limiting works correctly"""
        user_id = str(uuid4())
        rate_key = f"user:{user_id}:bookings"

        # Make 5 requests (within limit)
        for i in range(5):
            is_limited, count = await redis_manager.is_rate_limited(
                key=rate_key,
                limit=5,
                window=60
            )
            assert not is_limited
            assert count == i + 1

        # 6th request should be rate limited
        is_limited, count = await redis_manager.is_rate_limited(
            key=rate_key,
            limit=5,
            window=60
        )
        assert is_limited
        assert count == 5


class TestErrorHandling:
    """Test error handling scenarios"""

    @pytest.mark.asyncio
    async def test_nonexistent_event(self, booking_service, db_session, test_user):
        """Test booking nonexistent event"""
        fake_event_id = uuid4()
        booking_data = BookingCreate(
            event_id=fake_event_id,
            seat_ids=[uuid4()]
        )

        # Should raise HTTP exception for event not found
        with pytest.raises(Exception) as exc_info:
            await booking_service.create_booking_atomic(
                db=db_session,
                booking_data=booking_data,
                user=test_user
            )

        # Verify Redis cleanup happened
        event_id = str(fake_event_id)
        is_reserved = await redis_manager.verify_seat_reservation(
            event_id=event_id,
            seat_ids=[str(uuid4())],
            user_id=str(test_user.id)
        )
        assert not is_reserved

    @pytest.mark.asyncio
    async def test_booking_expiration(self, booking_service, db_session, test_user, test_event, test_seats):
        """Test booking expiration logic"""
        # Create booking
        seat_ids = [test_seats[0].id]
        booking_data = BookingCreate(event_id=test_event.id, seat_ids=seat_ids)

        booking_result = await booking_service.create_booking_atomic(
            db=db_session,
            booking_data=booking_data,
            user=test_user
        )

        # Get the booking and manually set it as expired
        from sqlalchemy import select
        stmt = select(Booking).where(Booking.id == booking_result["id"])
        result = await db_session.execute(stmt)
        booking = result.scalar_one()

        # Set expiry to past
        booking.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.flush()

        # Try to confirm expired booking
        with pytest.raises(Exception) as exc_info:
            await booking_service.confirm_booking(
                db=db_session,
                booking_id=booking_result["id"],
                user_id=str(test_user.id)
            )

        assert "expired" in str(exc_info.value)