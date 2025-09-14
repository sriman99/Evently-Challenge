"""
Base Pydantic schemas
"""

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional
from uuid import UUID


class BaseSchema(BaseModel):
    """Base schema with common configuration"""
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        arbitrary_types_allowed=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    )


class TimestampSchema(BaseSchema):
    """Schema with timestamp fields"""
    created_at: datetime
    updated_at: Optional[datetime] = None


class IDSchema(BaseSchema):
    """Schema with ID field"""
    id: UUID