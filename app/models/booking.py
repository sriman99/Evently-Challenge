"""
Booking and BookingSeat models
"""

from sqlalchemy import Column, String, ForeignKey, Enum, Numeric, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.models.base import BaseModel


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Booking(BaseModel):
    """
    Booking model for ticket reservations
    """
    __tablename__ = "bookings"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False, index=True)
    booking_code = Column(String(20), unique=True, nullable=False, index=True)
    status = Column(
        Enum(BookingStatus),
        default=BookingStatus.PENDING,
        nullable=False,
        index=True
    )
    total_amount = Column(Numeric(10, 2), nullable=False)
    expires_at = Column(DateTime(timezone=True))
    confirmed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    payment_reference = Column(String(255))  # Payment gateway reference

    # Relationships
    user = relationship("User", back_populates="bookings")
    event = relationship("Event", back_populates="bookings")
    booking_seats = relationship("BookingSeat", back_populates="booking", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="booking", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="booking", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Booking(id={self.id}, code={self.booking_code}, status={self.status}, amount={self.total_amount})>"


class BookingSeat(BaseModel):
    """
    Junction table for booking-seat relationship
    """
    __tablename__ = "booking_seats"

    booking_id = Column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False)
    seat_id = Column(UUID(as_uuid=True), ForeignKey("seats.id"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)

    # Relationships
    booking = relationship("Booking", back_populates="booking_seats")
    seat = relationship("Seat", back_populates="booking_seats")

    def __repr__(self):
        return f"<BookingSeat(booking_id={self.booking_id}, seat_id={self.seat_id}, price={self.price})>"