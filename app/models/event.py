"""
Event model
"""

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Enum, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql import and_
import enum

from app.models.base import BaseModel


class EventStatus(str, enum.Enum):
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Event(BaseModel):
    """
    Event model for concerts, shows, etc.
    """
    __tablename__ = "events"

    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    venue_id = Column(UUID(as_uuid=True), ForeignKey("venues.id"), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False)
    capacity = Column(Integer, nullable=False, index=True)
    # REMOVED: available_seats column - now computed in real-time from seat statuses
    # This eliminates the dual-truth data consistency issue
    status = Column(
        Enum(EventStatus),
        default=EventStatus.UPCOMING,
        nullable=False,
        index=True
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Relationships
    venue = relationship("Venue", back_populates="events")
    creator = relationship("User", back_populates="events_created")
    seats = relationship("Seat", back_populates="event", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="event", cascade="all, delete-orphan")
    waitlist_entries = relationship("Waitlist", back_populates="event", cascade="all, delete-orphan")
    analytics = relationship("Analytics", back_populates="event", cascade="all, delete-orphan")

    # Database constraints for data integrity
    __table_args__ = (
        # Ensure capacity is positive
        {'sqlite_autoincrement': True},
        # PostgreSQL check constraints will be added via migration
    )

    @hybrid_property
    def available_seats(self) -> int:
        """Computed property: real-time available seat count"""
        # Import here to avoid circular imports
        from app.models.seat import Seat, SeatStatus

        # Count seats that are NOT reserved or booked
        available_count = (
            select(func.count(Seat.id))
            .where(
                and_(
                    Seat.event_id == self.id,
                    Seat.status == SeatStatus.AVAILABLE
                )
            )
            .scalar_subquery()
        )
        return available_count

    @hybrid_property
    def reserved_seat_count(self) -> int:
        """Computed property: count of reserved/booked seats"""
        from app.models.seat import Seat, SeatStatus

        reserved_count = (
            select(func.count(Seat.id))
            .where(
                and_(
                    Seat.event_id == self.id,
                    Seat.status.in_([SeatStatus.RESERVED, SeatStatus.BOOKED])
                )
            )
            .scalar_subquery()
        )
        return reserved_count

    @property
    def utilization_percentage(self) -> float:
        """Calculate capacity utilization percentage"""
        if self.capacity == 0:
            return 0.0
        return (self.reserved_seat_count / self.capacity) * 100

    def __repr__(self):
        return f"<Event(id={self.id}, name={self.name}, status={self.status}, capacity={self.capacity})>"