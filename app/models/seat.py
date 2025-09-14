"""
Seat model
"""

from sqlalchemy import Column, String, Integer, ForeignKey, Enum, Numeric, UniqueConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.models.base import BaseModel


class SeatStatus(str, enum.Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    BOOKED = "booked"
    BLOCKED = "blocked"


class Seat(BaseModel):
    """
    Seat model for event seating with optimistic locking
    """
    __tablename__ = "seats"
    __table_args__ = (
        UniqueConstraint('event_id', 'section', 'row', 'seat_number', name='uq_event_seat'),
    )

    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False, index=True)
    section = Column(String(50))
    row = Column(String(10))
    seat_number = Column(String(10))
    price_tier = Column(String(20))
    price = Column(Numeric(10, 2), nullable=False)
    status = Column(
        Enum(SeatStatus),
        default=SeatStatus.AVAILABLE,
        nullable=False,
        index=True
    )
    # REMOVED: Optimistic locking (version column) - using consistent pessimistic locking strategy
    reserved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Track reservations
    reserved_at = Column(DateTime, nullable=True)  # Reservation timestamp

    # Relationships
    event = relationship("Event", back_populates="seats")
    booking_seats = relationship("BookingSeat", back_populates="seat")

    def __repr__(self):
        return f"<Seat(id={self.id}, event_id={self.event_id}, section={self.section}, row={self.row}, seat={self.seat_number}, status={self.status})>"