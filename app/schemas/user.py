"""
User schemas
"""

from pydantic import EmailStr, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
import re

from app.schemas.base import BaseSchema, IDSchema, TimestampSchema
from app.models.user import UserRole


class UserBase(BaseSchema):
    """Base user schema"""
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)


class UserCreate(UserBase):
    """User creation schema"""
    password: str = Field(..., min_length=8, max_length=100,
                         example="Demo123!")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "demo@evently.com",
                "full_name": "Demo User",
                "phone": "+1234567890",
                "password": "Demo123!"
            }
        }

    @field_validator('password')
    def validate_password(cls, v):
        if not re.match(r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$', v):
            raise ValueError('Password must contain at least one letter, one number, and one special character')
        return v

    @field_validator('phone')
    def validate_phone(cls, v):
        if v and not re.match(r'^\+?[1-9]\d{1,14}$', v):
            raise ValueError('Invalid phone number format')
        return v


class UserUpdate(BaseSchema):
    """User update schema"""
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)


class UserLogin(BaseSchema):
    """User login schema"""
    email: EmailStr
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "email": "admin@evently.com",
                "password": "Admin123!"
            }
        }


class UserResponse(UserBase, IDSchema, TimestampSchema):
    """User response schema"""
    role: UserRole
    is_active: bool
    stats: Optional[dict] = None


class UserStats(BaseSchema):
    """User statistics schema"""
    total_bookings: int = 0
    upcoming_events: int = 0
    total_spent: float = 0.0


class TokenResponse(BaseSchema):
    """Token response schema"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseSchema):
    """Token data schema"""
    user_id: Optional[UUID] = None
    email: Optional[str] = None
    role: Optional[UserRole] = None


class Token(BaseSchema):
    """Token schema with user info"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Optional["UserResponse"] = None


class TokenRefresh(BaseSchema):
    """Token refresh schema"""
    refresh_token: str


class PasswordChange(BaseSchema):
    """Password change schema"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator('new_password')
    def validate_password(cls, v):
        if not re.match(r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$', v):
            raise ValueError('Password must contain at least one letter, one number, and one special character')
        return v