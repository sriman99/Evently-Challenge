"""
User model
"""

from sqlalchemy import Column, String, Boolean, Enum
from sqlalchemy.orm import relationship
import enum

from app.models.base import BaseModel


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
    ORGANIZER = "organizer"


class User(BaseModel):
    """
    User model for authentication and profile
    """
    __tablename__ = "users"

    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(20))
    role = Column(
        Enum(UserRole),
        default=UserRole.USER,
        nullable=False
    )
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    bookings = relationship("Booking", back_populates="user", cascade="all, delete-orphan")
    events_created = relationship("Event", back_populates="creator", cascade="all, delete-orphan")
    waitlist_entries = relationship("Waitlist", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"