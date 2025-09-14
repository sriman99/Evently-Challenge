"""
Event management endpoints
"""

from typing import Any, List, Optional
from datetime import datetime
from uuid import UUID
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.core.redis import get_redis
from app.core.cache import cache_manager
from app.models.event import Event, EventStatus
from app.models.venue import Venue
from app.models.seat import Seat, SeatStatus
from app.schemas.event import EventResponse, EventDetail, EventCreate, EventUpdate
from app.schemas.seat import SeatResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[EventResponse])
async def get_events(
    db: AsyncSession = Depends(get_session),
    redis_client = Depends(get_redis),
    skip: int = Query(0, ge=0, alias="offset"),
    limit: int = Query(10, ge=1, le=100),
    page: Optional[int] = Query(None, ge=1),
    per_page: Optional[int] = Query(None, ge=1, le=100),
    status: Optional[EventStatus] = None,
    venue_id: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> Any:
    """
    Get list of events with filtering and pagination
    """
    # Handle both pagination parameter formats
    if page and per_page:
        skip = (page - 1) * per_page
        limit = per_page
    elif page and not per_page:
        per_page = 20  # default
        skip = (page - 1) * per_page
        limit = per_page

    # SECURITY FIX: Use secure cache manager with validation
    cache_params = {
        "skip": skip,
        "limit": limit,
        "status": status.value if status else None,
        "venue_id": venue_id,
        "search": search,
        "category": category,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "date_from": date_from,
        "date_to": date_to
    }

    cache_key = cache_manager._generate_cache_key("events", cache_params)

    # Try validated cache retrieval
    cached_events = await cache_manager.get_cache_data_only(
        cache_key=cache_key,
        response_model=EventResponse,
        is_list=True
    )

    if cached_events is not None:
        return cached_events

    # Build query
    query = select(Event).options(selectinload(Event.venue))

    # Apply filters
    filters = []
    if status:
        filters.append(Event.status == status)
    if venue_id:
        filters.append(Event.venue_id == venue_id)
    if search:
        filters.append(
            or_(
                Event.name.ilike(f"%{search}%"),
                Event.description.ilike(f"%{search}%")
            )
        )
    # Support both date parameter formats
    if start_date:
        filters.append(Event.start_time >= start_date)
    if end_date:
        filters.append(Event.end_time <= end_date)
    # SECURITY FIX: Secure date parsing with strict validation
    if date_from:
        try:
            # Strict validation: only allow ISO format with limited characters
            import re
            if not re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})$', date_from):
                raise ValueError("Invalid date format")

            # Safe parsing after validation
            date_from_clean = date_from.replace('Z', '+00:00')
            date_from_dt = datetime.fromisoformat(date_from_clean)
            filters.append(Event.start_time >= date_from_dt)
        except (ValueError, AttributeError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date_from format. Expected ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)."
            )
    if date_to:
        try:
            # Strict validation: only allow ISO format with limited characters
            import re
            if not re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})$', date_to):
                raise ValueError("Invalid date format")

            # Safe parsing after validation
            date_to_clean = date_to.replace('Z', '+00:00')
            date_to_dt = datetime.fromisoformat(date_to_clean)
            filters.append(Event.start_time <= date_to_dt)
        except (ValueError, AttributeError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date_to format. Expected ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)."
            )

    if filters:
        query = query.where(and_(*filters))

    # Apply ordering and pagination
    query = query.order_by(Event.start_time).offset(skip).limit(limit)

    result = await db.execute(query)
    events = result.scalars().all()

    # SECURITY FIX: Convert to validated response models for caching
    event_responses = []
    for event in events:
        # Use Pydantic model to ensure validation
        try:
            event_response = EventResponse.model_validate(event)
            event_responses.append(event_response)
        except Exception as e:
            # Skip invalid events rather than failing entire request
            logger.warning(f"Invalid event data for event {event.id}: {e}")
            continue

    # Cache the validated results
    await cache_manager.set_validated_cache(
        cache_key=cache_key,
        data=event_responses,
        ttl=300  # 5 minutes
    )

    return event_responses


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Get detailed information about a specific event
    """
    stmt = (
        select(Event)
        .options(
            selectinload(Event.venue),
            selectinload(Event.seats)
        )
        .where(Event.id == event_id)
    )

    result = await db.execute(stmt)
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    return event


@router.get("/{event_id}/seats", response_model=List[SeatResponse])
async def get_event_seats(
    event_id: UUID,
    db: AsyncSession = Depends(get_session),
    section: Optional[str] = None,
    status: Optional[SeatStatus] = None
) -> Any:
    """
    Get available seats for an event
    """
    # Build query
    query = select(Seat).where(Seat.event_id == event_id)

    # Apply filters
    if section:
        query = query.where(Seat.section == section)
    if status:
        query = query.where(Seat.status == status)

    query = query.order_by(Seat.section, Seat.row, Seat.seat_number)

    result = await db.execute(query)
    seats = result.scalars().all()

    if not seats:
        # Verify event exists
        event_stmt = select(Event).where(Event.id == event_id)
        event_result = await db.execute(event_stmt)
        if not event_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found"
            )

    return seats


@router.get("/search/upcoming", response_model=List[EventResponse])
async def search_upcoming_events(
    q: Optional[str] = Query(None, description="Search query for event name or description"),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(10, ge=1, le=50)
) -> Any:
    """
    Search upcoming events
    """
    current_time = datetime.utcnow()

    # Base query for upcoming events
    query_conditions = [
        Event.start_time > current_time,
        Event.status == EventStatus.UPCOMING,
        Event.available_seats > 0
    ]

    # Add search condition if query provided
    if q:
        search_condition = or_(
            Event.name.ilike(f"%{q}%"),
            Event.description.ilike(f"%{q}%")
        )
        query_conditions.append(search_condition)

    stmt = (
        select(Event)
        .options(selectinload(Event.venue))
        .where(and_(*query_conditions))
        .order_by(Event.start_time)
        .limit(limit)
    )

    result = await db.execute(stmt)
    events = result.scalars().all()

    return events


@router.get("/search/popular", response_model=List[EventResponse])
async def get_popular_events(
    db: AsyncSession = Depends(get_session),
    limit: int = Query(10, ge=1, le=50)
) -> Any:
    """
    Get popular events based on booking count
    """
    from app.models.booking import Booking

    # Create a subquery to get booking counts per event
    booking_count_subq = (
        select(
            Booking.event_id,
            func.count(Booking.id).label('booking_count')
        )
        .where(Booking.status.in_(['confirmed', 'pending']))  # Only count valid bookings
        .group_by(Booking.event_id)
        .subquery()
    )

    # Main query to get events with their booking counts
    stmt = (
        select(Event)
        .options(selectinload(Event.venue))
        .outerjoin(booking_count_subq, Event.id == booking_count_subq.c.event_id)
        .where(Event.status == EventStatus.UPCOMING)
        .order_by(
            func.coalesce(booking_count_subq.c.booking_count, 0).desc(),
            Event.start_time  # Secondary sort by start time
        )
        .limit(limit)
    )

    result = await db.execute(stmt)
    events = result.scalars().all()

    return events


@router.get("/categories/list")
async def get_event_categories(
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Get list of available event categories
    """
    # This would typically come from a categories table
    # For now, returning mock categories
    categories = [
        {"id": "concerts", "name": "Concerts", "icon": "music"},
        {"id": "sports", "name": "Sports", "icon": "sports"},
        {"id": "theater", "name": "Theater", "icon": "theater"},
        {"id": "comedy", "name": "Comedy", "icon": "comedy"},
        {"id": "festivals", "name": "Festivals", "icon": "festival"},
        {"id": "conferences", "name": "Conferences", "icon": "conference"}
    ]

    return categories