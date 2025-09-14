"""
Performance and load tests for the Evently platform
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
import random
import statistics

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.user import User
from app.models.event import Event, EventStatus
from app.models.seat import Seat, SeatStatus
from app.models.booking import Booking, BookingStatus
from app.core.redis import redis_manager
from app.core.security import security_manager


@pytest.mark.performance
@pytest.mark.asyncio
class TestDatabasePerformance:
    """Test database query performance"""

    async def test_bulk_insert_performance(self, db_session, test_event):
        """Test performance of bulk seat insertion"""
        num_seats = 10000
        seats = []

        start_time = time.perf_counter()

        # Create seats in batches
        batch_size = 1000
        for batch_start in range(0, num_seats, batch_size):
            batch_seats = []
            for i in range(batch_start, min(batch_start + batch_size, num_seats)):
                section = f"Section_{i // 100}"
                row = f"Row_{(i // 10) % 10}"
                seat_number = str(i % 10)

                seat = Seat(
                    event_id=test_event.id,
                    section=section,
                    row=row,
                    seat_number=f"{i:05d}",
                    price_tier="General",
                    price=Decimal("50.00"),
                    status=SeatStatus.AVAILABLE
                )
                batch_seats.append(seat)

            db_session.add_all(batch_seats)
            await db_session.flush()
            seats.extend(batch_seats)

        await db_session.commit()
        end_time = time.perf_counter()

        elapsed_time = end_time - start_time
        seats_per_second = num_seats / elapsed_time

        print(f"\nBulk Insert Performance:")
        print(f"  Inserted {num_seats} seats in {elapsed_time:.2f} seconds")
        print(f"  Rate: {seats_per_second:.0f} seats/second")

        # Performance assertion
        assert elapsed_time < 10, f"Bulk insert too slow: {elapsed_time:.2f}s for {num_seats} seats"
        assert seats_per_second > 1000, f"Insert rate too low: {seats_per_second:.0f} seats/second"

    async def test_concurrent_read_performance(self, db_session, test_event, test_seats):
        """Test performance of concurrent read operations"""
        num_concurrent_reads = 100
        read_times = []

        async def read_available_seats():
            """Read available seats for an event"""
            start = time.perf_counter()

            stmt = select(Seat).filter_by(
                event_id=test_event.id,
                status=SeatStatus.AVAILABLE
            ).limit(100)
            result = await db_session.execute(stmt)
            seats = result.scalars().all()

            end = time.perf_counter()
            read_times.append(end - start)
            return len(seats)

        # Run concurrent reads
        start_time = time.perf_counter()
        tasks = [read_available_seats() for _ in range(num_concurrent_reads)]
        results = await asyncio.gather(*tasks)
        end_time = time.perf_counter()

        total_time = end_time - start_time
        avg_read_time = statistics.mean(read_times)
        p95_read_time = statistics.quantiles(read_times, n=20)[18]  # 95th percentile

        print(f"\nConcurrent Read Performance:")
        print(f"  {num_concurrent_reads} concurrent reads in {total_time:.2f} seconds")
        print(f"  Average read time: {avg_read_time*1000:.2f}ms")
        print(f"  P95 read time: {p95_read_time*1000:.2f}ms")

        # Performance assertions
        assert avg_read_time < 0.1, f"Average read time too high: {avg_read_time*1000:.2f}ms"
        assert p95_read_time < 0.2, f"P95 read time too high: {p95_read_time*1000:.2f}ms"

    async def test_complex_query_performance(self, db_session):
        """Test performance of complex analytical queries"""
        # Create test data
        venue_id = uuid4()
        event_ids = []

        for i in range(10):
            event = Event(
                name=f"Event_{i}",
                venue_id=venue_id,
                start_time=datetime.utcnow() + timedelta(days=i),
                end_time=datetime.utcnow() + timedelta(days=i, hours=3),
                capacity=1000,
                available_seats=1000 - (i * 100),
                status=EventStatus.UPCOMING,
                created_by=uuid4()
            )
            db_session.add(event)
            event_ids.append(event.id)

        await db_session.commit()

        # Complex aggregation query
        start_time = time.perf_counter()

        from sqlalchemy import func
        stmt = (
            select(
                Event.status,
                func.count(Event.id).label("event_count"),
                func.sum(Event.capacity).label("total_capacity"),
                func.avg(Event.available_seats).label("avg_available")
            )
            .group_by(Event.status)
            .having(func.count(Event.id) > 0)
        )

        result = await db_session.execute(stmt)
        analytics = result.all()

        end_time = time.perf_counter()
        query_time = end_time - start_time

        print(f"\nComplex Query Performance:")
        print(f"  Aggregation query completed in {query_time*1000:.2f}ms")

        # Performance assertion
        assert query_time < 0.5, f"Complex query too slow: {query_time*1000:.2f}ms"


@pytest.mark.performance
@pytest.mark.asyncio
class TestRedisPerformance:
    """Test Redis operation performance"""

    async def test_redis_lock_acquisition_performance(self, redis_client):
        """Test performance of distributed lock acquisition"""
        num_locks = 1000
        lock_times = []
        release_times = []

        for i in range(num_locks):
            resource = f"perf_test_{i}"
            identifier = str(uuid4())

            # Measure lock acquisition
            start = time.perf_counter()
            lock = await redis_manager.acquire_lock(resource, identifier, ttl=1)
            lock_time = time.perf_counter() - start
            lock_times.append(lock_time)

            if lock:
                # Measure lock release
                start = time.perf_counter()
                await redis_manager.release_lock(resource, identifier)
                release_time = time.perf_counter() - start
                release_times.append(release_time)

        avg_lock_time = statistics.mean(lock_times) * 1000
        avg_release_time = statistics.mean(release_times) * 1000
        p95_lock_time = statistics.quantiles(lock_times, n=20)[18] * 1000

        print(f"\nRedis Lock Performance:")
        print(f"  Average lock acquisition: {avg_lock_time:.2f}ms")
        print(f"  Average lock release: {avg_release_time:.2f}ms")
        print(f"  P95 lock acquisition: {p95_lock_time:.2f}ms")

        # Performance assertions
        assert avg_lock_time < 10, f"Lock acquisition too slow: {avg_lock_time:.2f}ms"
        assert avg_release_time < 10, f"Lock release too slow: {avg_release_time:.2f}ms"

    async def test_redis_cache_performance(self, redis_client):
        """Test Redis cache read/write performance"""
        num_operations = 1000
        write_times = []
        read_times = []

        # Test data
        test_data = {
            "event_id": str(uuid4()),
            "seats": [{"id": str(uuid4()), "price": 100.00} for _ in range(10)],
            "metadata": {"created_at": datetime.utcnow().isoformat()}
        }

        # Write performance
        for i in range(num_operations):
            key = f"cache_test_{i}"
            start = time.perf_counter()
            await redis_manager.set(key, test_data, ttl=60)
            write_times.append(time.perf_counter() - start)

        # Read performance
        for i in range(num_operations):
            key = f"cache_test_{i}"
            start = time.perf_counter()
            await redis_manager.get(key)
            read_times.append(time.perf_counter() - start)

        avg_write = statistics.mean(write_times) * 1000
        avg_read = statistics.mean(read_times) * 1000

        print(f"\nRedis Cache Performance:")
        print(f"  Average write: {avg_write:.2f}ms")
        print(f"  Average read: {avg_read:.2f}ms")
        print(f"  Operations/second: {1000/avg_write:.0f} writes, {1000/avg_read:.0f} reads")

        # Performance assertions
        assert avg_write < 5, f"Cache write too slow: {avg_write:.2f}ms"
        assert avg_read < 2, f"Cache read too slow: {avg_read:.2f}ms"


@pytest.mark.performance
@pytest.mark.asyncio
class TestBookingSystemPerformance:
    """Test overall booking system performance"""

    async def test_concurrent_booking_throughput(self, db_session, test_event):
        """Test booking system throughput under load"""
        num_users = 100
        seats_per_user = 2
        booking_times = []
        successful_bookings = 0
        failed_bookings = 0

        # Create enough seats
        seats = []
        for i in range(num_users * seats_per_user * 2):  # Create extra seats
            seat = Seat(
                event_id=test_event.id,
                section="General",
                row=str(i // 20),
                seat_number=str(i % 20),
                price=Decimal("50.00"),
                status=SeatStatus.AVAILABLE
            )
            seats.append(seat)
        db_session.add_all(seats)
        await db_session.commit()

        async def simulate_booking(user_id: int):
            """Simulate a complete booking flow"""
            nonlocal successful_bookings, failed_bookings

            try:
                start = time.perf_counter()

                # Select random available seats
                stmt = select(Seat).filter_by(
                    event_id=test_event.id,
                    status=SeatStatus.AVAILABLE
                ).limit(seats_per_user)
                result = await db_session.execute(stmt)
                available_seats = result.scalars().all()

                if len(available_seats) < seats_per_user:
                    failed_bookings += 1
                    return

                # Acquire locks for selected seats
                locks = []
                for seat in available_seats:
                    lock_id = await redis_manager.acquire_lock(
                        f"seat:{seat.id}",
                        f"user_{user_id}",
                        ttl=5
                    )
                    if lock_id:
                        locks.append((seat.id, lock_id))
                    else:
                        # Release any acquired locks
                        for s_id, l_id in locks:
                            await redis_manager.release_lock(f"seat:{s_id}", l_id)
                        failed_bookings += 1
                        return

                # Create booking
                booking = Booking(
                    user_id=uuid4(),
                    event_id=test_event.id,
                    booking_code=f"PERF_{user_id:05d}",
                    status=BookingStatus.CONFIRMED,
                    total_amount=Decimal(seats_per_user * 50.00)
                )
                db_session.add(booking)

                # Update seat status
                for seat in available_seats:
                    seat.status = SeatStatus.BOOKED

                await db_session.commit()

                # Release locks
                for seat_id, lock_id in locks:
                    await redis_manager.release_lock(f"seat:{seat_id}", lock_id)

                booking_time = time.perf_counter() - start
                booking_times.append(booking_time)
                successful_bookings += 1

            except Exception as e:
                failed_bookings += 1
                await db_session.rollback()

        # Run concurrent bookings
        start_time = time.perf_counter()
        tasks = [simulate_booking(i) for i in range(num_users)]
        await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.perf_counter() - start_time

        if booking_times:
            avg_booking_time = statistics.mean(booking_times)
            p95_booking_time = statistics.quantiles(booking_times, n=20)[18] if len(booking_times) > 20 else max(booking_times)
            throughput = successful_bookings / total_time
        else:
            avg_booking_time = 0
            p95_booking_time = 0
            throughput = 0

        print(f"\nBooking System Performance:")
        print(f"  Total users: {num_users}")
        print(f"  Successful bookings: {successful_bookings}")
        print(f"  Failed bookings: {failed_bookings}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {throughput:.1f} bookings/second")
        print(f"  Average booking time: {avg_booking_time*1000:.2f}ms")
        print(f"  P95 booking time: {p95_booking_time*1000:.2f}ms")

        # Performance assertions
        assert throughput > 10, f"Throughput too low: {throughput:.1f} bookings/second"
        assert avg_booking_time < 1.0, f"Average booking time too high: {avg_booking_time*1000:.2f}ms"


@pytest.mark.performance
@pytest.mark.asyncio
class TestSecurityPerformance:
    """Test security operations performance"""

    async def test_password_hashing_performance(self):
        """Test password hashing performance"""
        num_operations = 100
        hash_times = []
        verify_times = []

        password = "TestPassword123!"

        # Hash performance
        for _ in range(num_operations):
            start = time.perf_counter()
            hashed = security_manager.hash_password(password)
            hash_times.append(time.perf_counter() - start)

        # Verify performance
        hashed_password = security_manager.hash_password(password)
        for _ in range(num_operations):
            start = time.perf_counter()
            security_manager.verify_password(password, hashed_password)
            verify_times.append(time.perf_counter() - start)

        avg_hash = statistics.mean(hash_times) * 1000
        avg_verify = statistics.mean(verify_times) * 1000

        print(f"\nSecurity Performance:")
        print(f"  Average hash time: {avg_hash:.2f}ms")
        print(f"  Average verify time: {avg_verify:.2f}ms")

        # bcrypt is intentionally slow, but should still be reasonable
        assert avg_hash < 200, f"Hashing too slow: {avg_hash:.2f}ms"
        assert avg_verify < 200, f"Verification too slow: {avg_verify:.2f}ms"

    async def test_jwt_token_performance(self):
        """Test JWT token generation and validation performance"""
        num_operations = 1000
        create_times = []
        decode_times = []

        data = {"sub": "user123", "email": "test@example.com", "role": "user"}

        # Token creation performance
        for _ in range(num_operations):
            start = time.perf_counter()
            token = security_manager.create_access_token(data)
            create_times.append(time.perf_counter() - start)

        # Token decoding performance
        token = security_manager.create_access_token(data)
        for _ in range(num_operations):
            start = time.perf_counter()
            security_manager.decode_token(token)
            decode_times.append(time.perf_counter() - start)

        avg_create = statistics.mean(create_times) * 1000
        avg_decode = statistics.mean(decode_times) * 1000

        print(f"\nJWT Performance:")
        print(f"  Average token creation: {avg_create:.2f}ms")
        print(f"  Average token decode: {avg_decode:.2f}ms")
        print(f"  Tokens/second: {1000/avg_create:.0f} create, {1000/avg_decode:.0f} decode")

        # JWT operations should be very fast
        assert avg_create < 1, f"Token creation too slow: {avg_create:.2f}ms"
        assert avg_decode < 1, f"Token decode too slow: {avg_decode:.2f}ms"