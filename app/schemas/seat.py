"""
Seat schemas for request/response models
"""

from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field
import uuid
import enum


class SeatStatus(str, enum.Enum):
    AVAILABLE = "available"
    BOOKED = "booked"
    RESERVED = "reserved"
    LOCKED = "locked"


class SeatBase(BaseModel):
    section: str = Field(..., min_length=1, max_length=10)
    row: str = Field(..., min_length=1, max_length=10)
    seat_number: str = Field(..., min_length=1, max_length=10)
    price: Decimal = Field(..., gt=0)
    status: SeatStatus = SeatStatus.AVAILABLE


class SeatCreate(SeatBase):
    event_id: uuid.UUID


class SeatUpdate(BaseModel):
    price: Optional[Decimal] = Field(None, gt=0)
    status: Optional[SeatStatus] = None


class SeatResponse(SeatBase):
    id: uuid.UUID
    event_id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class SeatReservation(BaseModel):
    event_id: uuid.UUID
    seat_ids: List[uuid.UUID]