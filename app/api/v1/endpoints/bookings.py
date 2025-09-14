"""
Production-ready booking management endpoints with hybrid concurrency control
"""

from typing import Any, List
from datetime import datetime, timedelta, timezone
import uuid
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import StaleDataError

from app.core.database import get_session, db_manager
from app.core.redis import redis_manager
from app.core.security import get_current_user
from app.core.metrics import metrics_collector
from app.core.saga import saga_orchestrator, BookingSaga
from app.models.user import User
from app.models.event import Event
from app.models.booking import Booking, BookingStatus, BookingSeat
from app.models.seat import Seat, SeatStatus
from app.schemas.booking import BookingCreate, BookingResponse, BookingDetail
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class BookingError(Exception):
    """Custom booking errors for better error handling"""
    pass


class SeatUnavailableError(BookingError):
    """Seats are not available for booking"""
    pass


class ReservationError(BookingError):
    """Redis reservation failed - seats already reserved by another user"""
    pass


class ProductionBookingService:
    """
    Production-ready booking service with Saga pattern for true atomicity
    Eliminates cross-system consistency issues identified in QA analysis
    """

    def __init__(self):
        self.redis_manager = redis_manager
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        self.booking_saga = BookingSaga(saga_orchestrator, redis_manager, db_manager)

    async def create_booking_atomic(
        self,
        db: AsyncSession,
        booking_data: BookingCreate,
        user: User
    ) -> dict:
        """
        Create booking using Saga pattern for true distributed transaction atomicity.

        This eliminates the critical cross-system consistency issues identified in QA:
        - Prevents Redis-PostgreSQL state mismatches
        - Ensures proper compensation if any step fails
        - Maintains ACID properties across distributed components
        """
        event_id = str(booking_data.event_id)
        seat_ids = [str(sid) for sid in booking_data.seat_ids]

        self.logger.info(f"Starting Saga-based booking for user {user.id}, event {event_id}")

        # Track metrics for this booking operation
        async with metrics_collector.track_booking_operation("create_booking_saga"):
            # Execute booking saga
            success, result = await self.booking_saga.create_booking_saga(
                event_id=event_id,
                seat_ids=seat_ids,
                user_id=str(user.id),
                booking_data=booking_data.dict()
            )

            if success:
                self.logger.info(f"Booking saga completed successfully: {result}")

                # CRITICAL FIX: Use existing db session instead of new transaction
                # The saga has already committed, so we use a fresh read-only query
                booking_id = result['booking_id']
                booking_stmt = (
                    select(Booking)
                    .options(
                        joinedload(Booking.event).joinedload(Event.venue),
                        joinedload(Booking.booking_seats).joinedload(BookingSeat.seat)
                    )
                    .where(Booking.id == booking_id)
                )

                # Use the provided db session for consistency
                booking_result = await db.execute(booking_stmt)
                complete_booking = booking_result.unique().scalar_one_or_none()

                if not complete_booking:
                    # This should not happen if Saga worked correctly
                    self.logger.error(f"Booking {booking_id} not found after successful Saga execution")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail={
                            "error_type": "data_consistency_error",
                            "message": "Booking creation succeeded but booking not found",
                            "support_reference": f"consistency_error_{uuid.uuid4().hex[:8]}"
                        }
                    )

                return self._format_booking_response(complete_booking)
            else:
                # Saga failed - all compensations already executed
                self.logger.error(f"Booking saga failed: {result}")

                if "no longer available" in str(result):
                    raise SeatUnavailableError(str(result))
                elif "reservation failed" in str(result):
                    raise ReservationError(str(result))
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Booking creation failed"
                    )

    async def confirm_booking(
        self,
        db: AsyncSession,
        booking_id: str,
        user_id: str,
        payment_reference: str = None
    ) -> dict:
        """
        Confirm booking after payment with proper seat status transition
        """
        async with self.db_manager.transaction(db):
            # Get booking with optimistic locking
            booking_stmt = (
                select(Booking)
                .options(joinedload(Booking.booking_seats).joinedload(BookingSeat.seat))
                .where(
                    and_(
                        Booking.id == booking_id,
                        Booking.user_id == user_id,
                        Booking.status == BookingStatus.PENDING
                    )
                )
                .with_for_update()
            )

            booking_result = await db.execute(booking_stmt)
            booking = booking_result.scalar_one_or_none()

            if not booking:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found or already processed"
                )

            # Check if booking has expired - do this BEFORE making changes
            current_time = datetime.now(timezone.utc)
            if current_time > booking.expires_at:
                # Mark as expired within the same transaction
                booking.status = BookingStatus.EXPIRED
                # Release seats back to available
                for booking_seat in booking.booking_seats:
                    seat = booking_seat.seat
                    seat.status = SeatStatus.AVAILABLE
                    seat.reserved_by = None
                    seat.reserved_at = None

                # Commit the expiration change
                await db.commit()

                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail={
                        "error_type": "booking_expired",
                        "message": "Booking has expired and has been automatically cancelled",
                        "expired_at": booking.expires_at.isoformat()
                    }
                )

            # Confirm booking
            booking.status = BookingStatus.CONFIRMED
            booking.confirmed_at = datetime.now(timezone.utc)
            if payment_reference:
                booking.payment_reference = payment_reference

            # Update seats from RESERVED to BOOKED
            for booking_seat in booking.booking_seats:
                seat = booking_seat.seat
                seat.status = SeatStatus.BOOKED

            # Release Redis reservations
            event_id = str(booking.event_id)
            seat_ids = [str(bs.seat_id) for bs in booking.booking_seats]
            await self.redis_manager.release_seat_reservations(
                event_id=event_id,
                seat_ids=seat_ids,
                user_id=str(user_id)
            )

            self.logger.info(f"Booking confirmed: {booking.booking_code}")
            return {"message": "Booking confirmed successfully", "booking_code": booking.booking_code}

    async def cancel_booking(
        self,
        db: AsyncSession,
        booking_id: str,
        user_id: str
    ) -> dict:
        """
        Cancel booking with proper cleanup and seat release
        """
        async with self.db_manager.transaction(db):
            booking_stmt = (
                select(Booking)
                .options(
                    joinedload(Booking.event),
                    joinedload(Booking.booking_seats).joinedload(BookingSeat.seat)
                )
                .where(
                    and_(
                        Booking.id == booking_id,
                        Booking.user_id == user_id,
                        Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED])
                    )
                )
                .with_for_update()
            )

            booking_result = await db.execute(booking_stmt)
            booking = booking_result.scalar_one_or_none()

            if not booking:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found or cannot be cancelled"
                )

            # Check cancellation policy for confirmed bookings
            if booking.status == BookingStatus.CONFIRMED:
                if datetime.now(timezone.utc) > booking.event.start_time - timedelta(hours=24):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot cancel confirmed booking less than 24 hours before event"
                    )

            # Cancel booking
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = datetime.now(timezone.utc)

            # Release seats back to available
            for booking_seat in booking.booking_seats:
                seat = booking_seat.seat
                seat.status = SeatStatus.AVAILABLE
                seat.reserved_by = None
                seat.reserved_at = None

            # Note: Event available_seats now computed from seat statuses - no manual update needed

            # Clean up Redis reservations
            event_id = str(booking.event_id)
            seat_ids = [str(bs.seat_id) for bs in booking.booking_seats]
            await self.redis_manager.release_seat_reservations(
                event_id=event_id,
                seat_ids=seat_ids,
                user_id=str(user_id)
            )

            self.logger.info(f"Booking cancelled: {booking.booking_code}")
            return {"message": "Booking cancelled successfully", "booking_id": booking_id}

    # REMOVED: _expire_booking method - expiration now handled inline to prevent race conditions

    def _format_booking_response(self, booking: Booking) -> dict:
        """Format booking for API response"""
        return {
            "id": str(booking.id),
            "booking_code": booking.booking_code,
            "event": {
                "id": str(booking.event.id),
                "name": booking.event.name,
                "start_time": booking.event.start_time,
                "venue_name": booking.event.venue.name,
                "venue_city": booking.event.venue.city,
            },
            "seats": [
                {
                    "id": str(bs.seat.id),
                    "section": bs.seat.section,
                    "row": bs.seat.row,
                    "seat_number": bs.seat.seat_number,
                    "price": float(bs.price)
                }
                for bs in booking.booking_seats
            ],
            "total_amount": float(booking.total_amount),
            "status": booking.status.value,
            "expires_at": booking.expires_at,
            "confirmed_at": booking.confirmed_at,
            "created_at": booking.created_at,
            "updated_at": booking.updated_at
        }


# Initialize production service
booking_service = ProductionBookingService()


@router.post("/", response_model=BookingResponse)
async def create_booking(
    booking_data: BookingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Create a new booking with production-grade concurrency control
    """
    try:
        # Rate limiting check
        rate_limited, current_count = await redis_manager.is_rate_limited(
            f"user:{current_user.id}:bookings",
            limit=5,  # Max 5 booking attempts per minute
            window=60
        )

        if rate_limited:
            await metrics_collector.record_rate_limit_hit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many booking attempts. Current: {current_count}/5 per minute"
            )

        # Create booking using production service
        result = await booking_service.create_booking_atomic(
            db, booking_data, current_user
        )

        return result

    except ReservationError as e:
        # HTTP 423 Locked - Resource is temporarily locked (Redis reservations)
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "error_type": "reservation_failed",
                "message": str(e),
                "retry_after": 5  # Suggest retry after 5 seconds
            }
        )
    except SeatUnavailableError as e:
        # HTTP 409 Conflict - Seats no longer available (database state)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_type": "seats_unavailable",
                "message": str(e),
                "suggest_alternatives": True
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_booking: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_type": "internal_error",
                "message": "Booking service temporarily unavailable",
                "support_reference": f"booking_error_{uuid.uuid4().hex[:8]}"
            }
        )


@router.post("/{booking_id}/confirm")
async def confirm_booking(
    booking_id: str,
    payment_reference: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Confirm booking after payment
    """
    try:
        result = await booking_service.confirm_booking(
            db=db,
            booking_id=booking_id,
            user_id=str(current_user.id),
            payment_reference=payment_reference
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in confirm_booking: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Confirmation service temporarily unavailable"
        )


@router.post("/{booking_id}/cancel")
async def cancel_booking(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Cancel a booking
    """
    try:
        result = await booking_service.cancel_booking(
            db=db,
            booking_id=booking_id,
            user_id=str(current_user.id)
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in cancel_booking: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cancellation service temporarily unavailable"
        )


@router.get("/", response_model=List[BookingResponse])
async def get_user_bookings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    skip: int = 0,
    limit: int = 100,
    status_filter: BookingStatus = None
) -> Any:
    """
    Get user's booking history with optional status filtering
    """
    try:
        # Build query with optional status filter
        query = (
            select(Booking)
            .options(
                joinedload(Booking.event).joinedload(Event.venue),
                joinedload(Booking.booking_seats).joinedload(BookingSeat.seat)
            )
            .where(Booking.user_id == current_user.id)
        )

        if status_filter:
            query = query.where(Booking.status == status_filter)

        query = (
            query.order_by(Booking.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await db.execute(query)
        bookings = result.unique().scalars().all()

        return [booking_service._format_booking_response(booking) for booking in bookings]

    except Exception as e:
        logger.error(f"Error fetching user bookings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving bookings"
        )


@router.get("/{booking_id}", response_model=BookingDetail)
async def get_booking(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Get specific booking details
    """
    try:
        stmt = (
            select(Booking)
            .options(
                joinedload(Booking.event).joinedload(Event.venue),
                joinedload(Booking.booking_seats).joinedload(BookingSeat.seat)
            )
            .where(
                and_(
                    Booking.id == booking_id,
                    Booking.user_id == current_user.id
                )
            )
        )

        result = await db.execute(stmt)
        booking = result.unique().scalar_one_or_none()

        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )

        return booking_service._format_booking_response(booking)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching booking {booking_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving booking"
        )