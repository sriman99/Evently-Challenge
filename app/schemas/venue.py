"""
Venue schemas for request/response models
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class VenueBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: str = Field(..., min_length=1, max_length=500)
    city: str = Field(..., min_length=1, max_length=100)
    state: Optional[str] = Field(None, min_length=2, max_length=50)
    postal_code: Optional[str] = Field(None, min_length=1, max_length=20)
    country: str = Field(..., min_length=1, max_length=100)
    capacity: int = Field(..., gt=0)


class VenueCreate(VenueBase):
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Music Hall",
                "address": "789 Arts District, Chicago, IL 60601",
                "city": "Chicago",
                "state": "IL",
                "postal_code": "60601",
                "country": "USA",
                "capacity": 800
            }
        }


class VenueUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = Field(None, min_length=1, max_length=500)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    state: Optional[str] = Field(None, min_length=2, max_length=50)
    postal_code: Optional[str] = Field(None, min_length=1, max_length=20)
    country: Optional[str] = Field(None, min_length=1, max_length=100)
    capacity: Optional[int] = Field(None, gt=0)


class VenueResponse(VenueBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class VenueDetail(VenueResponse):
    events: List["EventResponse"] = []

    class Config:
        from_attributes = True


# Import to avoid circular dependency
from app.schemas.event import EventResponse
VenueDetail.model_rebuild()