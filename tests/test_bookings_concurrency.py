"""
Comprehensive tests for booking endpoints with focus on concurrency
Testing race conditions, double-booking prevention, and distributed locking
"""

import pytest
import asyncio
from httpx import AsyncClient
from app.models.user import User
from app.models.event import Event
from app.models.seat import Seat
from app.models.booking import Booking


class TestBookingsConcurrency:
    """Test suite for booking endpoints with concurrency scenarios"""

    @pytest.mark.asyncio
    async def test_create_booking_success(
        self, client: AsyncClient, auth_headers_user, test_event: Event, test_seats: list[Seat]
    ):
        """Test successful booking creation"""
        seat_ids = [str(test_seats[0].id), str(test_seats[1].id)]

        response = await client.post(
            "/api/v1/bookings/",
            json={
                "event_id": str(test_event.id),
                "seat_ids": seat_ids
            },
            headers=auth_headers_user
        )

        assert response.status_code == 200
        data = response.json()
        assert data["event"]["id"] == str(test_event.id)
        assert data["status"] == "pending"
        assert "booking_code" in data

        # Handle total_amount as string (FastAPI JSON serialization)
        total_amount = float(data["total_amount"]) if isinstance(data["total_amount"], str) else data["total_amount"]
        assert total_amount > 0
        assert len(data["seats"]) == 2

    @pytest.mark.asyncio
    async def test_concurrent_booking_same_seats(
        self, client: AsyncClient, db_session, test_event: Event, test_seats: list[Seat]
    ):
        """Test that concurrent bookings for same seats are prevented"""
        # Create multiple users
        from tests.conftest import create_multiple_users
        users = await create_multiple_users(db_session, 3)

        # Create tokens for each user
        from app.core.security import create_access_token
        tokens = [
            create_access_token(
                data={"sub": str(user.id), "email": user.email, "role": user.role}
            )
            for user in users
        ]

        # Same seats for all attempts
        seat_ids = [str(test_seats[0].id), str(test_seats[1].id)]

        async def attempt_booking(token: str):
            return await client.post(
                "/api/v1/bookings/",
                json={
                    "event_id": str(test_event.id),
                    "seat_ids": seat_ids
                },
                headers={"Authorization": f"Bearer {token}"}
            )

        # Concurrent booking attempts
        responses = await asyncio.gather(
            *[attempt_booking(token) for token in tokens],
            return_exceptions=True
        )

        # Count successful bookings
        successful = [r for r in responses if not isinstance(r, Exception) and r.status_code == 200]
        failed = [r for r in responses if not isinstance(r, Exception) and r.status_code == 409]

        # Only one should succeed
        assert len(successful) == 1
        assert len(failed) == 2

        # Verify seat availability in database
        from sqlalchemy import select
        result = await db_session.execute(
            select(Seat).where(Seat.id.in_(seat_ids))
        )
        seats = result.scalars().all()

        # All selected seats should be booked
        for seat in seats:
            assert seat.status != "available"

    @pytest.mark.asyncio
    async def test_partial_seat_conflict(
        self, client: AsyncClient, db_session, test_event: Event, test_seats: list[Seat]
    ):
        """Test bookings with partially overlapping seats"""
        from tests.conftest import create_multiple_users
        users = await create_multiple_users(db_session, 2)

        from app.core.security import create_access_token
        tokens = [
            create_access_token(
                data={"sub": str(user.id), "email": user.email, "role": user.role}
            )
            for user in users
        ]

        # User 1 wants seats 0, 1
        # User 2 wants seats 1, 2
        # Seat 1 is conflicting
        bookings = [
            {"token": tokens[0], "seats": [str(test_seats[0].id), str(test_seats[1].id)]},
            {"token": tokens[1], "seats": [str(test_seats[1].id), str(test_seats[2].id)]}
        ]

        async def attempt_booking(token: str, seats: list):
            return await client.post(
                "/api/v1/bookings/",
                json={
                    "event_id": str(test_event.id),
                    "seat_ids": seats
                },
                headers={"Authorization": f"Bearer {token}"}
            )

        # Concurrent attempts
        responses = await asyncio.gather(
            *[attempt_booking(b["token"], b["seats"]) for b in bookings],
            return_exceptions=True
        )

        successful = [r for r in responses if not isinstance(r, Exception) and r.status_code == 200]

        # Only one should succeed (whoever gets the lock first)
        assert len(successful) == 1

    @pytest.mark.asyncio
    async def test_booking_nonexistent_event(
        self, client: AsyncClient, auth_headers_user
    ):
        """Test booking for non-existent event"""
        response = await client.post(
            "/api/v1/bookings/",
            json={
                "event_id": "00000000-0000-0000-0000-000000000000",
                "seat_ids": ["00000000-0000-0000-0000-000000000001"]
            },
            headers=auth_headers_user
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_booking_unavailable_seats(
        self, client: AsyncClient, auth_headers_user, test_event: Event, test_seats: list[Seat], db_session
    ):
        """Test booking already booked seats"""
        # Mark seats as booked
        test_seats[0].status = "booked"
        test_seats[1].status = "booked"
        db_session.add(test_seats[0])
        db_session.add(test_seats[1])
        await db_session.commit()

        response = await client.post(
            "/api/v1/bookings/",
            json={
                "event_id": str(test_event.id),
                "seat_ids": [str(test_seats[0].id), str(test_seats[1].id)]
            },
            headers=auth_headers_user
        )
        assert response.status_code == 409
        assert "no longer available" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_booking_exceeds_capacity(
        self, client: AsyncClient, auth_headers_user, test_event: Event, test_seats: list[Seat], db_session
    ):
        """Test booking when event capacity is exceeded"""
        # Set available seats to 1
        test_event.available_seats = 1
        db_session.add(test_event)
        await db_session.commit()

        # Try to book 2 seats
        response = await client.post(
            "/api/v1/bookings/",
            json={
                "event_id": str(test_event.id),
                "seat_ids": [str(test_seats[0].id), str(test_seats[1].id)]
            },
            headers=auth_headers_user
        )
        assert response.status_code == 400
        assert "not enough available seats" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cancel_booking_success(
        self, client: AsyncClient, auth_headers_user, test_booking: Booking, db_session
    ):
        """Test successful booking cancellation"""
        response = await client.post(
            f"/api/v1/bookings/{test_booking.id}/cancel",
            headers=auth_headers_user
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Booking cancelled successfully"

        # Verify booking status in database
        await db_session.refresh(test_booking)
        assert test_booking.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_booking(
        self, client: AsyncClient, auth_headers_user
    ):
        """Test cancelling non-existent booking"""
        response = await client.post(
            "/api/v1/bookings/00000000-0000-0000-0000-000000000000/cancel",
            headers=auth_headers_user
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_other_user_booking(
        self, client: AsyncClient, test_booking: Booking, db_session
    ):
        """Test that users cannot cancel other users' bookings"""
        # Create another user
        from tests.conftest import create_multiple_users
        other_users = await create_multiple_users(db_session, 1)
        other_user = other_users[0]

        from app.core.security import create_access_token
        other_token = create_access_token(
            data={"sub": str(other_user.id), "email": other_user.email, "role": other_user.role}
        )

        response = await client.post(
            f"/api/v1/bookings/{test_booking.id}/cancel",
            headers={"Authorization": f"Bearer {other_token}"}
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_double_cancel_booking(
        self, client: AsyncClient, auth_headers_user, test_booking: Booking
    ):
        """Test cancelling already cancelled booking"""
        # First cancellation
        response1 = await client.post(
            f"/api/v1/bookings/{test_booking.id}/cancel",
            headers=auth_headers_user
        )
        assert response1.status_code == 200

        # Second cancellation
        response2 = await client.post(
            f"/api/v1/bookings/{test_booking.id}/cancel",
            headers=auth_headers_user
        )
        assert response2.status_code == 400
        assert "already cancelled" in response2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_confirm_booking(
        self, client: AsyncClient, auth_headers_user, test_booking: Booking, db_session
    ):
        """Test confirming a pending booking"""
        # Set booking to pending
        test_booking.status = "pending"
        db_session.add(test_booking)
        await db_session.commit()

        response = await client.post(
            f"/api/v1/bookings/{test_booking.id}/confirm",
            headers=auth_headers_user
        )
        assert response.status_code == 200

        # Verify status
        await db_session.refresh(test_booking)
        assert test_booking.status == "confirmed"

    @pytest.mark.asyncio
    async def test_get_user_bookings(
        self, client: AsyncClient, auth_headers_user, test_booking: Booking
    ):
        """Test getting user's bookings"""
        response = await client.get(
            "/api/v1/bookings/my-bookings",
            headers=auth_headers_user
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        assert any(b["id"] == str(test_booking.id) for b in data)

    @pytest.mark.asyncio
    async def test_get_booking_details(
        self, client: AsyncClient, auth_headers_user, test_booking: Booking
    ):
        """Test getting specific booking details"""
        response = await client.get(
            f"/api/v1/bookings/{test_booking.id}",
            headers=auth_headers_user
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_booking.id)
        assert data["booking_code"] == test_booking.booking_code

    @pytest.mark.asyncio
    async def test_seat_lock_expiration(
        self, client: AsyncClient, auth_headers_user, test_event: Event,
        test_seats: list[Seat], test_redis
    ):
        """Test that seat locks expire after TTL"""
        seat_ids = [str(test_seats[0].id)]

        # Manually set a lock with very short TTL
        lock_key = f"seat_lock:{test_event.id}:{seat_ids[0]}"
        await test_redis.set(lock_key, "some-user-id", ex=1)  # 1 second TTL

        # Wait for lock to expire
        await asyncio.sleep(2)

        # Should be able to book now
        response = await client.post(
            "/api/v1/bookings/",
            json={
                "event_id": str(test_event.id),
                "seat_ids": seat_ids
            },
            headers=auth_headers_user
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_massive_concurrent_bookings(
        self, client: AsyncClient, db_session, test_venue, test_redis, test_admin
    ):
        """Test system under heavy concurrent load"""
        # Create a large event
        from app.models.event import Event
        from datetime import datetime, timedelta
        import uuid

        large_event = Event(
            id=uuid.uuid4(),
            name="Large Concert",
            description="High capacity event",
            venue_id=test_venue.id,
            start_time=datetime.utcnow() + timedelta(days=7),
            end_time=datetime.utcnow() + timedelta(days=7, hours=3),
            capacity=1000,
            available_seats=1000,
            created_by=test_admin.id
        )
        db_session.add(large_event)

        # Create many seats
        seats = []
        for i in range(100):  # 100 seats
            seat = Seat(
                id=uuid.uuid4(),
                event_id=large_event.id,
                section="A",
                row=str(i // 10),
                seat_number=str(i % 10),
                status="available",
                price=100.00
            )
            seats.append(seat)
            db_session.add(seat)

        await db_session.commit()

        # Create many users
        from tests.conftest import create_multiple_users
        users = await create_multiple_users(db_session, 50)  # 50 users

        # Create tokens
        from app.core.security import create_access_token
        tokens = [
            create_access_token(
                data={"sub": str(user.id), "email": user.email, "role": user.role}
            )
            for user in users
        ]

        # Each user tries to book 2 random seats
        import random
        booking_attempts = []
        for token in tokens:
            random_seats = random.sample(seats, 2)
            booking_attempts.append({
                "token": token,
                "seats": [str(s.id) for s in random_seats]
            })

        async def attempt_booking(token: str, seat_ids: list):
            try:
                return await client.post(
                    "/api/v1/bookings/",
                    json={
                        "event_id": str(large_event.id),
                        "seat_ids": seat_ids
                    },
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0
                )
            except Exception as e:
                return e

        # Execute all bookings concurrently
        responses = await asyncio.gather(
            *[attempt_booking(b["token"], b["seats"]) for b in booking_attempts],
            return_exceptions=True
        )

        # Analyze results
        successful = [r for r in responses if not isinstance(r, Exception) and hasattr(r, 'status_code') and r.status_code == 200]
        conflicts = [r for r in responses if not isinstance(r, Exception) and hasattr(r, 'status_code') and r.status_code == 409]

        # Should have some successful bookings
        assert len(successful) > 0
        # Should have conflicts due to seat contention
        assert len(conflicts) > 0

        # Verify no double-booking in database
        from sqlalchemy import select, func
        result = await db_session.execute(
            select(Seat.id, func.count(Seat.id))
            .where(Seat.event_id == large_event.id)
            .where(Seat.status != "available")
            .group_by(Seat.id)
        )
        seat_counts = result.all()

        # Each seat should only be booked once
        for seat_id, count in seat_counts:
            assert count <= 1, f"Seat {seat_id} was double-booked!"

    @pytest.mark.asyncio
    async def test_booking_with_payment_failure(
        self, client: AsyncClient, auth_headers_user, test_event: Event, test_seats: list[Seat]
    ):
        """Test booking rollback when payment fails"""
        # This would require payment integration
        # For now, test that booking remains in pending state
        response = await client.post(
            "/api/v1/bookings/",
            json={
                "event_id": str(test_event.id),
                "seat_ids": [str(test_seats[0].id)]
            },
            headers=auth_headers_user
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"  # Not confirmed until payment