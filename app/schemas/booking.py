"""
Booking schemas
"""

from pydantic import Field, field_validator
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from app.schemas.base import BaseSchema, IDSchema, TimestampSchema
from app.models.booking import BookingStatus
from app.config import settings


class SeatSelection(BaseSchema):
    """Seat selection schema"""
    seat_id: UUID


class BookingCreate(BaseSchema):
    """Booking creation schema"""
    event_id: UUID
    seat_ids: List[UUID] = Field(..., min_items=1, max_items=settings.MAX_SEATS_PER_BOOKING)

    @field_validator('seat_ids')
    def validate_unique_seats(cls, v):
        if len(v) != len(set(v)):
            raise ValueError('Duplicate seat IDs not allowed')
        return v


class BookingConfirm(BaseSchema):
    """Booking confirmation schema"""
    payment_method: str = Field(..., min_length=1)
    payment_details: Dict[str, Any]


class BookingSeatResponse(BaseSchema):
    """Booking seat response schema"""
    section: Optional[str] = None
    row: Optional[str] = None
    seat_number: Optional[str] = None
    price: Decimal


class BookingEventResponse(BaseSchema):
    """Booking event response schema"""
    id: UUID
    name: str
    start_time: datetime
    venue_name: str
    venue_city: str


class BookingResponse(IDSchema, TimestampSchema):
    """Booking response schema"""
    booking_code: str
    event: BookingEventResponse
    seats: List[BookingSeatResponse]
    total_amount: Decimal
    status: BookingStatus
    expires_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    payment_url: Optional[str] = None


class BookingListResponse(BaseSchema):
    """Booking list response schema"""
    id: UUID
    booking_code: str
    event_name: str
    event_date: datetime
    venue_name: str
    seat_count: int
    total_amount: Decimal
    status: BookingStatus
    created_at: datetime


class BookingCancelResponse(BaseSchema):
    """Booking cancellation response schema"""
    booking_id: UUID
    status: str
    refund_status: Optional[str] = None
    refund_amount: Optional[Decimal] = None


class BookingDetail(BookingResponse):
    """Detailed booking response with all information"""
    user_id: UUID
    user_name: Optional[str] = None
    user_email: Optional[str] = None