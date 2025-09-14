"""
Waitlist model
"""

from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Waitlist(BaseModel):
    """
    Waitlist model for sold-out events
    """
    __tablename__ = "waitlist"
    __table_args__ = (
        UniqueConstraint('user_id', 'event_id', name='uq_user_event_waitlist'),
    )

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    notified_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="waitlist_entries")
    event = relationship("Event", back_populates="waitlist_entries")

    def __repr__(self):
        return f"<Waitlist(id={self.id}, user_id={self.user_id}, event_id={self.event_id}, position={self.position})>"