"""
Analytics model
"""

from sqlalchemy import Column, String, ForeignKey, Date
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Analytics(BaseModel):
    """
    Analytics model for aggregated metrics
    """
    __tablename__ = "analytics"

    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False, index=True)
    value = Column(JSONB, nullable=False)
    date = Column(Date, nullable=False, index=True)

    # Relationships
    event = relationship("Event", back_populates="analytics")

    def __repr__(self):
        return f"<Analytics(id={self.id}, event_id={self.event_id}, metric_type={self.metric_type}, date={self.date})>"