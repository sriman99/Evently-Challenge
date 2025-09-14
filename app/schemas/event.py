"""
Event schemas
"""

from pydantic import Field, field_validator
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from app.schemas.base import BaseSchema, IDSchema, TimestampSchema
from app.models.event import EventStatus


class VenueBase(BaseSchema):
    """Base venue schema"""
    name: str = Field(..., min_length=1, max_length=255)
    address: str
    city: str = Field(..., min_length=1, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: str = Field(..., min_length=1, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    capacity: int = Field(..., gt=0)


class VenueCreate(VenueBase):
    """Venue creation schema"""
    layout_config: Optional[Dict[str, Any]] = {}


class VenueResponse(VenueBase, IDSchema, TimestampSchema):
    """Venue response schema"""
    layout_config: Optional[Dict[str, Any]] = {}


class EventBase(BaseSchema):
    """Base event schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    venue_id: UUID
    start_time: datetime
    end_time: datetime
    capacity: int = Field(..., gt=0)


class EventCreate(EventBase):
    """Event creation schema"""
    seat_configuration: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Jazz Night at the Blue Note",
                "description": "An intimate evening of smooth jazz featuring local artists",
                "venue_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                "start_time": "2025-10-15T20:00:00Z",
                "end_time": "2025-10-15T23:00:00Z",
                "capacity": 150
            },
            "description": "To create an event: 1) GET /api/v1/venues/ to get a venue_id, 2) Use the actual UUID from the venues response"
        }

    @field_validator('end_time')
    def validate_end_time(cls, v, values):
        if 'start_time' in values.data and v <= values.data['start_time']:
            raise ValueError('End time must be after start time')
        return v


class EventUpdate(BaseSchema):
    """Event update schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[EventStatus] = None


class PriceTier(BaseSchema):
    """Price tier schema"""
    tier: str
    price: Decimal
    available: int


class EventResponse(EventBase, IDSchema, TimestampSchema):
    """Event response schema"""
    venue: VenueResponse
    status: EventStatus
    price_tiers: Optional[List[PriceTier]] = []


class EventListResponse(BaseSchema):
    """Event list response schema"""
    id: UUID
    name: str
    venue: Dict[str, Any]
    start_time: datetime
    end_time: datetime
    capacity: int
    available_seats: int
    status: EventStatus
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None


class EventSeatResponse(BaseSchema):
    """Event seat response schema"""
    id: UUID
    section: Optional[str] = None
    row: Optional[str] = None
    seat_number: Optional[str] = None
    price: Decimal
    status: str


class EventDetail(EventResponse):
    """Detailed event response with seats"""
    seats: Optional[List[EventSeatResponse]] = []


class SeatAvailability(BaseSchema):
    """Seat availability schema"""
    event_id: UUID
    sections: List[Dict[str, Any]]
    summary: Dict[str, Any]