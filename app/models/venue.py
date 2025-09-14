"""
Venue model
"""

from sqlalchemy import Column, String, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Venue(BaseModel):
    """
    Venue model for event locations
    """
    __tablename__ = "venues"

    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=False)
    city = Column(String(100), nullable=False, index=True)
    state = Column(String(100))
    country = Column(String(100), nullable=False)
    postal_code = Column(String(20))
    capacity = Column(Integer, nullable=False)
    layout_config = Column(JSONB, default={})

    # Relationships
    events = relationship("Event", back_populates="venue", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Venue(id={self.id}, name={self.name}, city={self.city}, capacity={self.capacity})>"