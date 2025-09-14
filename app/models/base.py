"""
Base model class with common fields
"""

from sqlalchemy import Column, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.core.database import Base


class BaseModel(Base):
    """
    Abstract base model with common fields
    """
    __abstract__ = True

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def dict(self):
        """Convert model to dictionary"""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }