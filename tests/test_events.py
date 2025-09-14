"""
Comprehensive tests for event endpoints
Testing search, filtering, capacity, and edge cases
"""

import pytest
import uuid
from httpx import AsyncClient
from datetime import datetime, timedelta
from app.models.event import Event
from app.models.venue import Venue


class TestEvents:
    """Test suite for event endpoints"""

    @pytest.mark.asyncio
    async def test_list_events(self, client: AsyncClient, multiple_events):
        """Test listing all events"""
        response = await client.get("/api/v1/events/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= len(multiple_events)  # Database may have additional events

        # Verify event structure
        for event in data:
            assert "id" in event
            assert "name" in event
            assert "venue" in event
            assert "start_time" in event
            assert "capacity" in event
            assert "available_seats" in event

    @pytest.mark.asyncio
    async def test_list_events_with_pagination(self, client: AsyncClient, multiple_events):
        """Test event listing with pagination"""
        # First page
        response = await client.get("/api/v1/events/?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2

        # Second page
        response = await client.get("/api/v1/events/?limit=2&offset=2")
        assert response.status_code == 200
        data2 = response.json()

        # Ensure different events
        if data and data2:
            assert data[0]["id"] != data2[0]["id"]

    @pytest.mark.asyncio
    async def test_filter_events_by_status(self, client: AsyncClient, db_session, test_venue, test_admin):
        """Test filtering events by status"""
        from app.models.event import EventStatus

        # Create events with different statuses
        completed_event = Event(
            id=uuid.uuid4(),
            name="Completed Event",
            venue_id=test_venue.id,
            start_time=datetime.utcnow() - timedelta(days=7),
            end_time=datetime.utcnow() - timedelta(days=6),
            capacity=100,
            available_seats=0,
            status=EventStatus.COMPLETED,  # Explicitly set status
            created_by=test_admin.id
        )

        upcoming_event = Event(
            id=uuid.uuid4(),
            name="Upcoming Event",
            venue_id=test_venue.id,
            start_time=datetime.utcnow() + timedelta(days=7),
            end_time=datetime.utcnow() + timedelta(days=7, hours=2),
            capacity=100,
            available_seats=100,
            status=EventStatus.UPCOMING,  # Explicitly set status
            created_by=test_admin.id
        )

        cancelled_event = Event(
            id=uuid.uuid4(),
            name="Cancelled Event",
            venue_id=test_venue.id,
            start_time=datetime.utcnow() + timedelta(days=14),
            end_time=datetime.utcnow() + timedelta(days=14, hours=2),
            capacity=100,
            available_seats=100,
            status=EventStatus.CANCELLED,  # Explicitly set status
            created_by=test_admin.id
        )

        db_session.add(completed_event)
        db_session.add(upcoming_event)
        db_session.add(cancelled_event)
        await db_session.commit()

        # First test: get all events to verify our events were created
        response_all = await client.get("/api/v1/events/")
        assert response_all.status_code == 200
        all_data = response_all.json()

        print(f"All events in database ({len(all_data)}):")
        our_events = [e for e in all_data if e['name'] in ['Completed Event', 'Upcoming Event', 'Cancelled Event']]
        for event in our_events:
            print(f"  - {event['name']}: status={event.get('status', 'UNKNOWN')}")

        # Test filtering by upcoming status
        response = await client.get("/api/v1/events/?status=upcoming")
        assert response.status_code == 200
        data = response.json()

        print(f"Filtered events for status=upcoming ({len(data)}):")
        for event in data[:5]:  # Show first 5 for debugging
            print(f"  - {event['name']}: status={event.get('status', 'UNKNOWN')}")

        # Should find our upcoming event
        upcoming_event_found = any(event["name"] == "Upcoming Event" for event in data)
        assert upcoming_event_found, f"Upcoming Event not found in filtered results"

        # Should not find completed or cancelled events in upcoming filter
        completed_event_found = any(event["name"] == "Completed Event" for event in data)
        cancelled_event_found = any(event["name"] == "Cancelled Event" for event in data)
        assert not completed_event_found, "Completed Event should not be in upcoming filter"
        assert not cancelled_event_found, "Cancelled Event should not be in upcoming filter"

    @pytest.mark.asyncio
    async def test_get_event_details(self, client: AsyncClient, test_event: Event):
        """Test getting specific event details"""
        response = await client.get(f"/api/v1/events/{test_event.id}")
        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(test_event.id)
        assert data["name"] == test_event.name
        assert data["description"] == test_event.description
        assert "venue" in data
        assert data["venue"]["id"] == str(test_event.venue_id)

    @pytest.mark.asyncio
    async def test_get_nonexistent_event(self, client: AsyncClient):
        """Test getting non-existent event"""
        response = await client.get("/api/v1/events/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_event_seats(self, client: AsyncClient, test_event: Event, test_seats):
        """Test getting available seats for an event"""
        response = await client.get(f"/api/v1/events/{test_event.id}/seats")
        assert response.status_code == 200
        data = response.json()

        assert len(data) == len(test_seats)

        # Verify seat structure
        for seat in data:
            assert "id" in seat
            assert "section" in seat
            assert "row" in seat
            assert "seat_number" in seat
            assert "status" in seat
            assert "price" in seat

    @pytest.mark.asyncio
    async def test_get_only_available_seats(self, client: AsyncClient, test_event: Event, test_seats, db_session):
        """Test that only available seats are returned"""
        from app.models.seat import SeatStatus
        # Mark some seats as unavailable
        test_seats[0].status = SeatStatus.BOOKED
        test_seats[1].status = SeatStatus.RESERVED
        db_session.add(test_seats[0])
        db_session.add(test_seats[1])
        await db_session.commit()

        response = await client.get(f"/api/v1/events/{test_event.id}/seats?status=available")
        assert response.status_code == 200
        data = response.json()

        # All returned seats should be available
        for seat in data:
            assert seat["status"] == "available"

        # Should have fewer seats than total
        assert len(data) == len(test_seats) - 2

    @pytest.mark.asyncio
    async def test_search_events(self, client: AsyncClient, multiple_events):
        """Test event search functionality"""
        response = await client.get("/api/v1/events/search/upcoming?q=Jazz")
        assert response.status_code == 200
        data = response.json()

        # Should find Jazz Night event
        assert any("jazz" in event["name"].lower() for event in data)

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, client: AsyncClient, multiple_events):
        """Test that search is case-insensitive"""
        response1 = await client.get("/api/v1/events/search/upcoming?q=JAZZ")
        response2 = await client.get("/api/v1/events/search/upcoming?q=jazz")

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Should return same results
        assert len(response1.json()) == len(response2.json())

    @pytest.mark.asyncio
    async def test_get_popular_events(self, client: AsyncClient, db_session, test_venue, test_user, test_admin):
        """Test getting popular events based on bookings"""
        # Create events with different booking counts
        from app.models.booking import Booking

        popular_event = Event(
            id=uuid.uuid4(),
            name="Popular Event",
            venue_id=test_venue.id,
            start_time=datetime.utcnow() + timedelta(days=7),
            end_time=datetime.utcnow() + timedelta(days=7, hours=2),
            capacity=100,
            available_seats=50,
            created_by=test_admin.id
        )

        unpopular_event = Event(
            id=uuid.uuid4(),
            name="Unpopular Event",
            venue_id=test_venue.id,
            start_time=datetime.utcnow() + timedelta(days=14),
            end_time=datetime.utcnow() + timedelta(days=14, hours=2),
            capacity=100,
            available_seats=95,
            created_by=test_admin.id
        )

        db_session.add(popular_event)
        db_session.add(unpopular_event)

        # Create bookings for popular event
        for i in range(5):
            booking = Booking(
                id=uuid.uuid4(),
                user_id=test_user.id,
                event_id=popular_event.id,
                booking_code=f"POP{uuid.uuid4().hex[:6].upper()}{i:02d}",  # Unique booking code
                total_amount=100.00,
                status="confirmed"
            )
            db_session.add(booking)

        # One booking for unpopular event
        booking = Booking(
            id=uuid.uuid4(),
            user_id=test_user.id,
            event_id=unpopular_event.id,
            booking_code=f"UNPOP{uuid.uuid4().hex[:6].upper()}",  # Unique booking code
            total_amount=100.00,
            status="confirmed"
        )
        db_session.add(booking)

        await db_session.commit()

        response = await client.get("/api/v1/events/search/popular")
        assert response.status_code == 200
        data = response.json()

        # Popular event should appear first
        if data:
            assert data[0]["name"] == "Popular Event"

    @pytest.mark.asyncio
    async def test_get_event_categories(self, client: AsyncClient):
        """Test getting event categories"""
        response = await client.get("/api/v1/events/categories/list")
        assert response.status_code == 200
        data = response.json()

        # API returns categories directly as a list
        assert isinstance(data, list)
        assert len(data) > 0

        # Verify category structure
        for category in data:
            assert "id" in category
            assert "name" in category
            assert "icon" in category

    @pytest.mark.asyncio
    async def test_filter_events_by_date_range(self, client: AsyncClient, db_session, test_venue, test_admin):
        """Test filtering events by date range"""

        # Create events in different time periods
        next_week = Event(
            id=uuid.uuid4(),
            name="Next Week Event",
            venue_id=test_venue.id,
            start_time=datetime.utcnow() + timedelta(days=7),
            end_time=datetime.utcnow() + timedelta(days=7, hours=2),
            capacity=100,
            available_seats=100,
            created_by=test_admin.id
        )

        next_month = Event(
            id=uuid.uuid4(),
            name="Next Month Event",
            venue_id=test_venue.id,
            start_time=datetime.utcnow() + timedelta(days=35),
            end_time=datetime.utcnow() + timedelta(days=35, hours=2),
            capacity=100,
            available_seats=100,
            created_by=test_admin.id
        )

        db_session.add(next_week)
        db_session.add(next_month)
        await db_session.commit()

        # Filter for next 2 weeks only with higher limit to see all events
        date_from = datetime.utcnow().isoformat()
        date_to = (datetime.utcnow() + timedelta(days=14)).isoformat()

        response = await client.get(
            f"/api/v1/events/?date_from={date_from}&date_to={date_to}&limit=100"
        )
        assert response.status_code == 200
        data = response.json()

        # Should include next week but not next month
        event_names = [e["name"] for e in data]
        assert "Next Week Event" in event_names
        assert "Next Month Event" not in event_names

    @pytest.mark.asyncio
    async def test_filter_events_by_venue(self, client: AsyncClient, db_session, test_admin):
        """Test filtering events by venue"""

        # Create two venues
        venue1 = Venue(
            id=uuid.uuid4(),
            name="Venue 1",
            address="123 St",
            city="City1",
            state="ST",
            country="USA",
            postal_code="12345",
            capacity=500
        )

        venue2 = Venue(
            id=uuid.uuid4(),
            name="Venue 2",
            address="456 Ave",
            city="City2",
            state="ST",
            country="USA",
            postal_code="67890",
            capacity=300
        )

        db_session.add(venue1)
        db_session.add(venue2)

        # Create events for different venues
        event1 = Event(
            id=uuid.uuid4(),
            name="Event at Venue 1",
            venue_id=venue1.id,
            start_time=datetime.utcnow() + timedelta(days=7),
            end_time=datetime.utcnow() + timedelta(days=7, hours=2),
            capacity=100,
            available_seats=100,
            created_by=test_admin.id
        )

        event2 = Event(
            id=uuid.uuid4(),
            name="Event at Venue 2",
            venue_id=venue2.id,
            start_time=datetime.utcnow() + timedelta(days=7),
            end_time=datetime.utcnow() + timedelta(days=7, hours=2),
            capacity=100,
            available_seats=100,
            created_by=test_admin.id
        )

        db_session.add(event1)
        db_session.add(event2)
        await db_session.commit()

        # Filter by venue1
        response = await client.get(f"/api/v1/events/?venue_id={venue1.id}")
        assert response.status_code == 200
        data = response.json()

        # Should only get events from venue1
        for event in data:
            assert event["venue_id"] == str(venue1.id)

    @pytest.mark.asyncio
    async def test_event_capacity_tracking(self, client: AsyncClient, test_event: Event, db_session, auth_headers_user, test_seats):
        """Test that event capacity is properly tracked with bookings"""
        initial_available = test_event.available_seats

        # Create a booking
        response = await client.post(
            "/api/v1/bookings/",
            json={
                "event_id": str(test_event.id),
                "seat_ids": [str(test_seats[0].id), str(test_seats[1].id)]
            },
            headers=auth_headers_user
        )
        assert response.status_code == 200

        # Check updated event
        response = await client.get(f"/api/v1/events/{test_event.id}")
        assert response.status_code == 200
        data = response.json()

        # Available seats should decrease
        assert data["available_seats"] == initial_available - 2

    @pytest.mark.asyncio
    async def test_invalid_event_id_format(self, client: AsyncClient):
        """Test handling of invalid UUID format"""
        response = await client.get("/api/v1/events/not-a-uuid")
        # Fixed: API now correctly returns 422 for invalid UUID validation per PDF requirements
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_event_sorting(self, client: AsyncClient, multiple_events):
        """Test that events are sorted by start time"""
        response = await client.get("/api/v1/events/")
        assert response.status_code == 200
        data = response.json()

        # Verify events are sorted by start_time
        start_times = [datetime.fromisoformat(e["start_time"].replace("Z", "+00:00")) for e in data]
        assert start_times == sorted(start_times)