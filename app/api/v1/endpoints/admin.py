"""
Admin management endpoints
"""

from typing import Any, List, Dict
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update, delete
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.core.security import get_current_user
from app.core.cache import cache_manager
from app.models.user import User, UserRole
from app.models.event import Event, EventStatus
from app.models.venue import Venue
from app.models.booking import Booking, BookingStatus
from app.models.seat import Seat, SeatStatus
from app.schemas.event import EventCreate, EventUpdate, EventResponse
from app.schemas.venue import VenueCreate, VenueUpdate, VenueResponse

router = APIRouter()


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to require admin role
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.ORGANIZER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


@router.get("/analytics/dashboard")
async def get_dashboard_analytics(
    db: AsyncSession = Depends(get_session),
    admin_user: User = Depends(require_admin),
    start_date: date = Query(None, description="Start date for analytics"),
    end_date: date = Query(None, description="End date for analytics")
) -> Dict:
    """
    Get admin dashboard analytics
    """
    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Total bookings
    bookings_count = await db.execute(
        select(func.count(Booking.id)).where(
            and_(
                Booking.created_at >= start_date,
                Booking.created_at <= end_date,
                Booking.status == BookingStatus.CONFIRMED
            )
        )
    )
    total_bookings = bookings_count.scalar() or 0

    # Total revenue
    revenue_result = await db.execute(
        select(func.sum(Booking.total_amount)).where(
            and_(
                Booking.created_at >= start_date,
                Booking.created_at <= end_date,
                Booking.status == BookingStatus.CONFIRMED
            )
        )
    )
    total_revenue = float(revenue_result.scalar() or 0)

    # Total events
    events_count = await db.execute(
        select(func.count(Event.id)).where(
            and_(
                Event.created_at >= start_date,
                Event.created_at <= end_date
            )
        )
    )
    total_events = events_count.scalar() or 0

    # Most popular events
    popular_events_stmt = (
        select(
            Event.id,
            Event.name,
            func.count(Booking.id).label("booking_count")
        )
        .join(Booking, Event.id == Booking.event_id)
        .where(
            and_(
                Booking.created_at >= start_date,
                Booking.created_at <= end_date,
                Booking.status == BookingStatus.CONFIRMED
            )
        )
        .group_by(Event.id, Event.name)
        .order_by(func.count(Booking.id).desc())
        .limit(5)
    )
    popular_events_result = await db.execute(popular_events_stmt)
    popular_events = [
        {"id": str(row[0]), "name": row[1], "bookings": row[2]}
        for row in popular_events_result
    ]

    # Capacity utilization
    capacity_stmt = select(
        func.avg(
            (Event.capacity - Event.available_seats) * 100.0 / Event.capacity
        )
    ).where(
        and_(
            Event.created_at >= start_date,
            Event.created_at <= end_date,
            Event.capacity > 0
        )
    )
    capacity_result = await db.execute(capacity_stmt)
    avg_capacity_utilization = float(capacity_result.scalar() or 0)

    # Cancellation rate
    total_bookings_all = await db.execute(
        select(func.count(Booking.id)).where(
            and_(
                Booking.created_at >= start_date,
                Booking.created_at <= end_date
            )
        )
    )
    total_all = total_bookings_all.scalar() or 0

    cancelled_bookings = await db.execute(
        select(func.count(Booking.id)).where(
            and_(
                Booking.created_at >= start_date,
                Booking.created_at <= end_date,
                Booking.status == BookingStatus.CANCELLED
            )
        )
    )
    total_cancelled = cancelled_bookings.scalar() or 0

    cancellation_rate = (total_cancelled / total_all * 100) if total_all > 0 else 0

    return {
        "period": {
            "start_date": str(start_date),
            "end_date": str(end_date)
        },
        "metrics": {
            "total_bookings": total_bookings,
            "total_revenue": total_revenue,
            "total_events": total_events,
            "avg_capacity_utilization": round(avg_capacity_utilization, 2),
            "cancellation_rate": round(cancellation_rate, 2)
        },
        "popular_events": popular_events
    }


@router.post("/events", response_model=EventResponse)
async def create_event(
    event_data: EventCreate,
    db: AsyncSession = Depends(get_session),
    admin_user: User = Depends(require_admin)
) -> Any:
    """
    Create a new event (Admin/Organizer only)
    """
    # Verify venue exists
    venue_stmt = select(Venue).where(Venue.id == event_data.venue_id)
    venue_result = await db.execute(venue_stmt)
    venue = venue_result.scalar_one_or_none()

    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )

    # Create event
    event = Event(
        **event_data.dict(),
        created_by=admin_user.id,
        status=EventStatus.UPCOMING
    )

    db.add(event)
    await db.flush()

    # Create seats to match event capacity exactly
    capacity = event.capacity
    base_price = 100.0

    # Calculate optimal seat distribution
    sections = ["General", "Premium", "VIP"]
    seats_created = 0

    # Distribute seats across sections proportionally
    seats_per_section = capacity // len(sections)
    remaining_seats = capacity % len(sections)

    for section_idx, section in enumerate(sections):
        section_capacity = seats_per_section
        if section_idx < remaining_seats:
            section_capacity += 1

        # Calculate rows and seats per row for this section
        target_seats_per_row = 20  # Reasonable default
        rows_needed = max(1, section_capacity // target_seats_per_row)
        actual_seats_per_row = section_capacity // rows_needed
        extra_seats = section_capacity % rows_needed

        section_price = base_price + (section_idx * 100)  # General: 100, Premium: 200, VIP: 300

        for row in range(1, rows_needed + 1):
            seats_in_this_row = actual_seats_per_row
            if row <= extra_seats:
                seats_in_this_row += 1

            for seat_num in range(1, seats_in_this_row + 1):
                seat = Seat(
                    event_id=event.id,
                    section=section,
                    row=str(row),
                    seat_number=str(seat_num),
                    price=section_price,
                    status=SeatStatus.AVAILABLE
                )
                db.add(seat)
                seats_created += 1

    # Verify we created exactly the right number of seats
    assert seats_created == capacity, f"Seat count mismatch: created {seats_created}, expected {capacity}"

    await db.commit()
    await db.refresh(event)

    # CRITICAL FIX: Invalidate events cache after creation
    await cache_manager.invalidate_events_cache()

    return event


@router.put("/events/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: str,
    event_update: EventUpdate,
    db: AsyncSession = Depends(get_session),
    admin_user: User = Depends(require_admin)
) -> Any:
    """
    Update an event (Admin/Organizer only)
    """
    stmt = select(Event).where(Event.id == event_id)
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    # Only allow creator or admin to update
    if admin_user.role != UserRole.ADMIN and event.created_by != admin_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this event"
        )

    # Update event fields
    update_data = event_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)

    await db.commit()
    await db.refresh(event)

    # CRITICAL FIX: Invalidate event-specific and general cache after update
    await cache_manager.invalidate_event_cache(str(event.id))

    return event


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    db: AsyncSession = Depends(get_session),
    admin_user: User = Depends(require_admin)
) -> Any:
    """
    Delete an event (Admin only)
    """
    if admin_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete events"
        )

    stmt = select(Event).where(Event.id == event_id)
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    # Check if there are confirmed bookings
    bookings_stmt = select(func.count(Booking.id)).where(
        and_(
            Booking.event_id == event_id,
            Booking.status == BookingStatus.CONFIRMED
        )
    )
    bookings_result = await db.execute(bookings_stmt)
    confirmed_bookings = bookings_result.scalar() or 0

    if confirmed_bookings > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete event with {confirmed_bookings} confirmed bookings"
        )

    # Delete event (cascades to seats and bookings)
    await db.delete(event)
    await db.commit()

    # CRITICAL FIX: Invalidate all event-related cache after deletion
    await cache_manager.invalidate_events_cache()

    return {"message": "Event deleted successfully"}


@router.get("/users", response_model=List[Dict])
async def get_users(
    db: AsyncSession = Depends(get_session),
    admin_user: User = Depends(require_admin),
    skip: int = 0,
    limit: int = 100
) -> Any:
    """
    Get list of users (Admin only)
    """
    if admin_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view all users"
        )

    stmt = (
        select(User)
        .offset(skip)
        .limit(limit)
        .order_by(User.created_at.desc())
    )

    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat()
        }
        for user in users
    ]


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: UserRole,
    db: AsyncSession = Depends(get_session),
    admin_user: User = Depends(require_admin)
) -> Any:
    """
    Update user role (Admin only)
    """
    if admin_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can change user roles"
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.role = role
    await db.commit()

    return {"message": f"User role updated to {role.value}"}