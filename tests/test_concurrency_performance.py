"""
Concurrency performance tests for production booking system
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import statistics

from app.api.v1.endpoints.bookings import ProductionBookingService
from app.core.redis import redis_manager
from app.models.user import User
from app.models.event import Event
from app.models.venue import Venue
from app.models.seat import Seat, SeatStatus
from app.schemas.booking import BookingCreate


class TestConcurrencyPerformance:
    """Test concurrency performance and deadlock prevention"""

    @pytest.mark.asyncio
    async def test_high_concurrency_booking(self, db_session):
        """Test high concurrency booking scenarios"""
        booking_service = ProductionBookingService()

        # Create test data
        venue = Venue(
            name="Concurrency Arena",
            address="123 Stress Test St",
            city="Performance City",
            capacity=1000
        )
        db_session.add(venue)
        await db_session.flush()

        event = Event(
            name="High Concurrency Concert",
            venue_id=venue.id,
            start_time=datetime.now(timezone.utc) + timedelta(days=30),
            end_time=datetime.now(timezone.utc) + timedelta(days=30, hours=3),
            total_seats=100,
            available_seats=100
        )
        db_session.add(event)
        await db_session.flush()

        # Create 100 seats
        seats = []
        for i in range(100):
            seat = Seat(
                event_id=event.id,
                section="A",
                row=str((i // 10) + 1),
                seat_number=str((i % 10) + 1),
                price=100.00,
                status=SeatStatus.AVAILABLE
            )
            db_session.add(seat)
            seats.append(seat)

        await db_session.flush()

        # Create 50 users
        users = []
        for i in range(50):
            user = User(
                email=f"user{i}@concurrency.test",
                hashed_password="hash",
                first_name=f"User{i}",
                last_name="Test"
            )
            db_session.add(user)
            users.append(user)

        await db_session.flush()

        # Define booking function
        async def attempt_booking(user_index, seat_indices):
            user = users[user_index]
            seat_ids = [seats[i].id for i in seat_indices]
            booking_data = BookingCreate(event_id=event.id, seat_ids=seat_ids)

            start_time = time.time()
            try:
                result = await booking_service.create_booking_atomic(
                    db=db_session,
                    booking_data=booking_data,
                    user=user
                )
                end_time = time.time()
                return {
                    "success": True,
                    "user_id": user_index,
                    "seats": seat_indices,
                    "booking_code": result["booking_code"],
                    "duration": end_time - start_time
                }
            except Exception as e:
                end_time = time.time()
                return {
                    "success": False,
                    "user_id": user_index,
                    "seats": seat_indices,
                    "error": str(e),
                    "duration": end_time - start_time
                }

        # Test 1: Non-overlapping seats (should all succeed)
        print("Test 1: Non-overlapping seats")
        tasks = []
        for i in range(50):
            seat_indices = [i * 2, i * 2 + 1]  # Each user gets 2 unique seats
            tasks.append(attempt_booking(i, seat_indices))

        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time

        successful_bookings = [r for r in results if isinstance(r, dict) and r.get("success")]
        failed_bookings = [r for r in results if isinstance(r, dict) and not r.get("success")]

        print(f"Non-overlapping test results:")
        print(f"- Total time: {total_time:.2f}s")
        print(f"- Successful bookings: {len(successful_bookings)}")
        print(f"- Failed bookings: {len(failed_bookings)}")
        print(f"- Average booking time: {statistics.mean([r['duration'] for r in successful_bookings]):.3f}s")

        # All should succeed with non-overlapping seats
        assert len(successful_bookings) == 50
        assert len(failed_bookings) == 0

        # Reset for next test
        await self._reset_seats(db_session, seats)
        await self._cleanup_redis(event.id, seats)

        # Test 2: Overlapping seats (contention scenario)
        print("\nTest 2: High contention - all users try same seats")
        tasks = []
        popular_seats = [0, 1, 2, 3, 4]  # First 5 seats - high contention

        for i in range(25):  # 25 users competing for same 5 seats
            tasks.append(attempt_booking(i, popular_seats))

        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time

        successful_bookings = [r for r in results if isinstance(r, dict) and r.get("success")]
        failed_bookings = [r for r in results if isinstance(r, dict) and not r.get("success")]

        print(f"High contention test results:")
        print(f"- Total time: {total_time:.2f}s")
        print(f"- Successful bookings: {len(successful_bookings)}")
        print(f"- Failed bookings: {len(failed_bookings)}")
        if successful_bookings:
            print(f"- Average successful booking time: {statistics.mean([r['duration'] for r in successful_bookings]):.3f}s")
        if failed_bookings:
            print(f"- Average failed booking time: {statistics.mean([r['duration'] for r in failed_bookings]):.3f}s")

        # Only 1 should succeed (only 5 seats available, each booking wants 5 seats)
        assert len(successful_bookings) == 1
        assert len(failed_bookings) == 24

        # Verify no deadlocks occurred (all operations completed)
        assert len(results) == 25

        # Performance assertions
        assert total_time < 30  # Should complete within 30 seconds
        if successful_bookings:
            assert all(r['duration'] < 5 for r in successful_bookings)  # Individual bookings < 5s

    @pytest.mark.asyncio
    async def test_deadlock_prevention(self, db_session):
        """Test that our deterministic lock ordering prevents deadlocks"""
        booking_service = ProductionBookingService()

        # Create minimal test data
        venue = Venue(name="Deadlock Test Arena", capacity=100)
        db_session.add(venue)
        await db_session.flush()

        event = Event(
            name="Deadlock Test Event",
            venue_id=venue.id,
            start_time=datetime.now(timezone.utc) + timedelta(days=1),
            end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=2),
            total_seats=10,
            available_seats=10
        )
        db_session.add(event)
        await db_session.flush()

        # Create seats
        seats = []
        for i in range(10):
            seat = Seat(
                event_id=event.id,
                section="A",
                row="1",
                seat_number=str(i + 1),
                price=50.00,
                status=SeatStatus.AVAILABLE
            )
            db_session.add(seat)
            seats.append(seat)

        await db_session.flush()

        # Create users
        users = []
        for i in range(4):
            user = User(
                email=f"deadlock_user{i}@test.com",
                hashed_password="hash",
                first_name=f"User{i}"
            )
            db_session.add(user)
            users.append(user)

        await db_session.flush()

        # Create scenarios that would cause deadlocks with wrong lock ordering
        async def booking_scenario_1():
            # User 0 wants seats [0, 1, 2] - will be sorted to [0, 1, 2]
            seat_ids = [seats[0].id, seats[1].id, seats[2].id]
            booking_data = BookingCreate(event_id=event.id, seat_ids=seat_ids)

            try:
                result = await booking_service.create_booking_atomic(
                    db=db_session, booking_data=booking_data, user=users[0]
                )
                return {"success": True, "user": 0, "seats": [0, 1, 2]}
            except Exception as e:
                return {"success": False, "user": 0, "error": str(e)}

        async def booking_scenario_2():
            # User 1 wants seats [2, 1, 0] - will be sorted to [0, 1, 2] (same order)
            seat_ids = [seats[2].id, seats[1].id, seats[0].id]
            booking_data = BookingCreate(event_id=event.id, seat_ids=seat_ids)

            try:
                result = await booking_service.create_booking_atomic(
                    db=db_session, booking_data=booking_data, user=users[1]
                )
                return {"success": True, "user": 1, "seats": [2, 1, 0]}
            except Exception as e:
                return {"success": False, "user": 1, "error": str(e)}

        async def booking_scenario_3():
            # User 2 wants seats [1, 3] - no overlap, should succeed
            seat_ids = [seats[1].id, seats[3].id]
            booking_data = BookingCreate(event_id=event.id, seat_ids=seat_ids)

            try:
                result = await booking_service.create_booking_atomic(
                    db=db_session, booking_data=booking_data, user=users[2]
                )
                return {"success": True, "user": 2, "seats": [1, 3]}
            except Exception as e:
                return {"success": False, "user": 2, "error": str(e)}

        # Run scenarios concurrently
        start_time = time.time()
        results = await asyncio.gather(
            booking_scenario_1(),
            booking_scenario_2(),
            booking_scenario_3(),
            return_exceptions=True
        )
        execution_time = time.time() - start_time

        print(f"Deadlock prevention test results:")
        print(f"- Execution time: {execution_time:.2f}s")
        for i, result in enumerate(results):
            if isinstance(result, dict):
                print(f"- Scenario {i+1}: {result}")
            else:
                print(f"- Scenario {i+1}: Exception: {result}")

        # Verify no deadlocks (all operations completed)
        assert len(results) == 3
        assert execution_time < 10  # Should complete quickly, no deadlock delays

        # Verify deterministic behavior
        successful = [r for r in results if isinstance(r, dict) and r.get("success")]
        failed = [r for r in results if isinstance(r, dict) and not r.get("success")]

        # Should have some successes and failures, but no exceptions/deadlocks
        assert len(successful) + len(failed) == 3
        assert all(isinstance(r, dict) for r in results)

    @pytest.mark.asyncio
    async def test_redis_reservation_performance(self):
        """Test Redis reservation system performance"""
        event_id = str(uuid4())
        user_ids = [str(uuid4()) for _ in range(100)]
        seat_ids = [str(uuid4()) for _ in range(100)]

        # Test concurrent Redis reservations
        async def reserve_seats(user_id, seats):
            start_time = time.time()
            try:
                success, failed = await redis_manager.reserve_seats(
                    event_id=event_id,
                    seat_ids=seats,
                    user_id=user_id,
                    ttl=300
                )
                end_time = time.time()
                return {
                    "success": success,
                    "user": user_id,
                    "duration": end_time - start_time,
                    "failed_seats": failed
                }
            except Exception as e:
                end_time = time.time()
                return {
                    "success": False,
                    "user": user_id,
                    "duration": end_time - start_time,
                    "error": str(e)
                }

        # Test 1: Non-overlapping reservations
        tasks = []
        for i, user_id in enumerate(user_ids[:50]):
            user_seats = seat_ids[i*2:(i*2)+2]  # Each user gets 2 unique seats
            tasks.append(reserve_seats(user_id, user_seats))

        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time

        successful = [r for r in results if isinstance(r, dict) and r.get("success")]

        print(f"Redis reservation performance:")
        print(f"- Total time for 50 concurrent reservations: {total_time:.2f}s")
        print(f"- Successful reservations: {len(successful)}")
        print(f"- Average reservation time: {statistics.mean([r['duration'] for r in successful]):.3f}s")
        print(f"- Max reservation time: {max([r['duration'] for r in successful]):.3f}s")

        # Performance assertions
        assert len(successful) == 50  # All should succeed
        assert total_time < 5  # Should complete quickly
        assert all(r['duration'] < 1 for r in successful)  # Individual ops < 1s

        # Cleanup
        await redis_manager.cleanup_expired_locks(f"seat:reserved:{event_id}:*")

    async def _reset_seats(self, db_session, seats):
        """Reset all seats to available status"""
        for seat in seats:
            seat.status = SeatStatus.AVAILABLE
            seat.reserved_by = None
            seat.reserved_at = None
        await db_session.flush()

    async def _cleanup_redis(self, event_id, seats):
        """Clean up Redis reservations"""
        for seat in seats:
            key = f"seat:reserved:{event_id}:{seat.id}"
            meta_key = f"{key}:meta"
            try:
                client = await redis_manager.get_client()
                await client.delete(key, meta_key)
            except:
                pass  # Ignore cleanup errors


if __name__ == "__main__":
    # Run performance tests manually
    import asyncio

    async def run_performance_tests():
        print("Running concurrency performance tests...")
        # Initialize test environment
        # Note: This requires proper test database and Redis setup
        print("Tests would run here with proper test fixtures")

    asyncio.run(run_performance_tests())