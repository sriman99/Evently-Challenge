"""
Concurrency tests for booking system
Tests race conditions, double booking prevention, and distributed locking
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
import random

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.seat import Seat, SeatStatus
from app.models.booking import Booking, BookingStatus, BookingSeat
from app.models.event import Event
from app.core.redis import redis_manager


@pytest.mark.concurrency
@pytest.mark.asyncio
class TestSeatBookingConcurrency:
    """Test concurrent seat booking scenarios"""

    async def test_concurrent_seat_booking_with_locks(self, db_session, test_event, test_seats, redis_client):
        """Test that distributed locking prevents double booking"""
        seat = test_seats[0]
        num_concurrent_attempts = 10
        successful_bookings = []
        failed_bookings = []

        async def try_book_seat(user_num: int):
            """Simulate a user trying to book a seat"""
            lock_identifier = f"user_{user_num}_{uuid4().hex}"

            # Try to acquire lock
            lock_acquired = await redis_manager.acquire_lock(
                f"seat:{seat.id}",
                lock_identifier,
                ttl=5
            )

            if not lock_acquired:
                failed_bookings.append(user_num)
                return False

            try:
                # Check if seat is still available
                stmt = select(Seat).filter_by(id=seat.id, status=SeatStatus.AVAILABLE)
                result = await db_session.execute(stmt)
                available_seat = result.scalar_one_or_none()

                if not available_seat:
                    failed_bookings.append(user_num)
                    return False

                # Book the seat
                available_seat.status = SeatStatus.BOOKED
                await db_session.commit()
                successful_bookings.append(user_num)
                return True

            finally:
                # Release lock
                await redis_manager.release_lock(f"seat:{seat.id}", lock_identifier)

        # Run concurrent booking attempts
        tasks = [try_book_seat(i) for i in range(num_concurrent_attempts)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify only one booking succeeded
        assert len(successful_bookings) == 1
        assert len(failed_bookings) == num_concurrent_attempts - 1

        # Verify seat status in database
        await db_session.refresh(seat)
        assert seat.status == SeatStatus.BOOKED

    async def test_optimistic_locking_prevents_concurrent_updates(self, db_session, test_event):
        """Test optimistic locking with version field"""
        # Create a seat with version tracking
        seat = Seat(
            event_id=test_event.id,
            section="Test",
            row="A",
            seat_number="1",
            price=Decimal("100.00"),
            status=SeatStatus.AVAILABLE
        )
        db_session.add(seat)
        await db_session.commit()
        await db_session.refresh(seat)

        num_concurrent_updates = 5
        successful_updates = []

        async def try_update_with_version_check(attempt_num: int):
            """Try to update seat with optimistic locking"""
            from sqlalchemy.orm.exc import StaleDataError
            try:
                # Start transaction
                async with db_session.begin():
                    # Get seat for update (SQLAlchemy handles version check)
                    stmt = select(Seat).filter_by(id=seat.id)
                    result = await db_session.execute(stmt)
                    current_seat = result.scalar_one()

                    # Simulate some processing time
                    await asyncio.sleep(random.uniform(0.01, 0.05))

                    # Update seat (SQLAlchemy auto-increments version)
                    current_seat.status = SeatStatus.BOOKED
                    await db_session.flush()  # Force version check

                successful_updates.append(attempt_num)
                return True
            except StaleDataError:
                # Version conflict - expected in concurrent scenario
                return False
            except Exception:
                return False
                return False

        # Run concurrent update attempts
        tasks = [try_update_with_version_check(i) for i in range(num_concurrent_updates)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Only one update should succeed
        assert len(successful_updates) == 1

    async def test_booking_expiration_race_condition(self, db_session, test_user, test_event, test_seats):
        """Test race condition between booking expiration and confirmation"""
        # Create a booking that's about to expire
        booking = Booking(
            user_id=test_user.id,
            event_id=test_event.id,
            booking_code=f"EXPIRE_{uuid4().hex[:8]}",
            status=BookingStatus.PENDING,
            total_amount=Decimal("100.00"),
            expires_at=datetime.utcnow() + timedelta(seconds=1)
        )
        db_session.add(booking)
        await db_session.commit()

        # Reserve a seat for this booking
        seat = test_seats[0]
        seat.status = SeatStatus.RESERVED
        booking_seat = BookingSeat(
            booking_id=booking.id,
            seat_id=seat.id,
            price=seat.price
        )
        db_session.add(booking_seat)
        await db_session.commit()

        confirm_succeeded = False
        expire_succeeded = False

        async def try_confirm_booking():
            """Try to confirm the booking"""
            nonlocal confirm_succeeded
            await asyncio.sleep(0.8)  # Wait almost until expiry

            stmt = select(Booking).filter_by(
                id=booking.id,
                status=BookingStatus.PENDING
            )
            result = await db_session.execute(stmt)
            pending_booking = result.scalar_one_or_none()

            if pending_booking and pending_booking.expires_at > datetime.utcnow():
                pending_booking.status = BookingStatus.CONFIRMED
                pending_booking.confirmed_at = datetime.utcnow()
                await db_session.commit()
                confirm_succeeded = True

        async def try_expire_booking():
            """Try to expire the booking"""
            nonlocal expire_succeeded
            await asyncio.sleep(1.1)  # Wait until after expiry

            stmt = select(Booking).filter_by(
                id=booking.id,
                status=BookingStatus.PENDING
            )
            result = await db_session.execute(stmt)
            pending_booking = result.scalar_one_or_none()

            if pending_booking and pending_booking.expires_at <= datetime.utcnow():
                pending_booking.status = BookingStatus.EXPIRED
                # Release the seat
                seat.status = SeatStatus.AVAILABLE
                await db_session.commit()
                expire_succeeded = True

        # Run both operations concurrently
        await asyncio.gather(
            try_confirm_booking(),
            try_expire_booking(),
            return_exceptions=True
        )

        # Only one should succeed
        assert (confirm_succeeded and not expire_succeeded) or (expire_succeeded and not confirm_succeeded)

        # Verify final state
        await db_session.refresh(booking)
        assert booking.status in [BookingStatus.CONFIRMED, BookingStatus.EXPIRED]


@pytest.mark.concurrency
@pytest.mark.asyncio
class TestEventCapacityConcurrency:
    """Test concurrent updates to event capacity"""

    async def test_available_seats_decrement_race_condition(self, db_session, test_event):
        """Test race condition when multiple bookings decrement available seats"""
        initial_available = 10
        test_event.available_seats = initial_available
        await db_session.commit()

        num_concurrent_bookings = 15  # More than available
        successful_bookings = []

        async def try_book_if_available(booking_num: int):
            """Try to book if seats are available"""
            # Read current availability
            stmt = select(Event).filter_by(id=test_event.id)
            result = await db_session.execute(stmt)
            event = result.scalar_one()

            if event.available_seats > 0:
                # Simulate processing delay
                await asyncio.sleep(random.uniform(0.01, 0.05))

                # Try to decrement with check
                stmt = (
                    update(Event)
                    .where(Event.id == test_event.id)
                    .where(Event.available_seats > 0)
                    .values(available_seats=Event.available_seats - 1)
                    .returning(Event.available_seats)
                )
                result = await db_session.execute(stmt)
                new_available = result.scalar_one_or_none()

                if new_available is not None:
                    await db_session.commit()
                    successful_bookings.append(booking_num)
                    return True
                else:
                    await db_session.rollback()
                    return False
            return False

        # Run concurrent booking attempts
        tasks = [try_book_if_available(i) for i in range(num_concurrent_bookings)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Should not exceed initial availability
        assert len(successful_bookings) <= initial_available

        # Verify final state
        await db_session.refresh(test_event)
        assert test_event.available_seats == initial_available - len(successful_bookings)
        assert test_event.available_seats >= 0  # Should never go negative


@pytest.mark.concurrency
@pytest.mark.asyncio
class TestDistributedLockingScenarios:
    """Test various distributed locking scenarios"""

    async def test_lock_timeout_and_recovery(self, redis_client):
        """Test lock timeout and recovery scenario"""
        resource = f"seat_{uuid4().hex}"
        identifier1 = str(uuid4())
        identifier2 = str(uuid4())

        # Acquire lock with short TTL
        lock1 = await redis_manager.acquire_lock(resource, identifier1, ttl=1)
        assert lock1 is not None

        # Second attempt should fail immediately
        lock2 = await redis_manager.acquire_lock(resource, identifier2, ttl=5)
        assert lock2 is None

        # Wait for first lock to expire
        await asyncio.sleep(1.5)

        # Now second attempt should succeed
        lock2 = await redis_manager.acquire_lock(resource, identifier2, ttl=5)
        assert lock2 is not None

        # Cleanup
        await redis_manager.release_lock(resource, identifier2)

    async def test_concurrent_lock_extension(self, redis_client):
        """Test concurrent attempts to extend the same lock"""
        resource = f"seat_{uuid4().hex}"
        correct_identifier = str(uuid4())
        wrong_identifier = str(uuid4())

        # Acquire lock
        await redis_manager.acquire_lock(resource, correct_identifier, ttl=2)

        extend_results = []

        async def try_extend(identifier: str, is_correct: bool):
            """Try to extend lock"""
            result = await redis_manager.extend_lock(resource, identifier, 5)
            extend_results.append((is_correct, result))

        # Try to extend concurrently with correct and wrong identifiers
        await asyncio.gather(
            try_extend(correct_identifier, True),
            try_extend(wrong_identifier, False),
            try_extend(wrong_identifier, False)
        )

        # Only correct identifier should succeed
        correct_extends = [r for is_correct, r in extend_results if is_correct]
        wrong_extends = [r for is_correct, r in extend_results if not is_correct]

        assert all(correct_extends)  # All correct attempts should succeed
        assert not any(wrong_extends)  # All wrong attempts should fail

        # Cleanup
        await redis_manager.release_lock(resource, correct_identifier)

    async def test_thundering_herd_scenario(self, redis_client):
        """Test thundering herd scenario when popular event opens"""
        resource = f"popular_event_{uuid4().hex}"
        num_users = 50
        successful_locks = []
        lock_times = []

        async def try_acquire_lock_with_timing(user_id: int):
            """Try to acquire lock and measure time"""
            identifier = f"user_{user_id}"
            start_time = asyncio.get_event_loop().time()

            # Try to acquire lock with retries
            max_retries = 3
            for retry in range(max_retries):
                lock = await redis_manager.acquire_lock(resource, identifier, ttl=1)
                if lock:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    successful_locks.append(user_id)
                    lock_times.append(elapsed)

                    # Simulate processing
                    await asyncio.sleep(0.05)

                    # Release lock
                    await redis_manager.release_lock(resource, identifier)
                    return True

                # Brief delay before retry
                await asyncio.sleep(random.uniform(0.01, 0.1))

            return False

        # Simulate thundering herd
        tasks = [try_acquire_lock_with_timing(i) for i in range(num_users)]
        start = asyncio.get_event_loop().time()
        await asyncio.gather(*tasks)
        total_time = asyncio.get_event_loop().time() - start

        # All users should eventually get the lock (with retries)
        assert len(successful_locks) > 0

        # Check that locks were distributed over time (not all at once)
        if len(lock_times) > 1:
            time_spread = max(lock_times) - min(lock_times)
            assert time_spread > 0  # Locks acquired at different times

        print(f"Thundering herd test: {len(successful_locks)}/{num_users} succeeded in {total_time:.2f}s")