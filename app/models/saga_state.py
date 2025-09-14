"""
Saga state persistence model
"""

from sqlalchemy import Column, String, Text, DateTime, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID, JSON
import enum
from datetime import datetime, timezone

from app.models.base import BaseModel


class SagaStateStatus(str, enum.Enum):
    STARTED = "started"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"


class SagaState(BaseModel):
    """
    Persistent storage for Saga transaction state
    Enables recovery of incomplete transactions after server restart
    """
    __tablename__ = "saga_states"

    saga_id = Column(String(100), unique=True, nullable=False, index=True)
    saga_name = Column(String(255), nullable=False)
    status = Column(Enum(SagaStateStatus), nullable=False, index=True)

    # Serialized context and step data
    context = Column(JSON)
    steps_data = Column(JSON)

    # Progress tracking
    current_step_index = Column(Integer, default=0)
    completed_steps = Column(Integer, default=0)

    # Timing
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True))

    # Error information
    error_message = Column(Text)
    last_retry_at = Column(DateTime(timezone=True))
    retry_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<SagaState(saga_id={self.saga_id}, name={self.saga_name}, status={self.status})>"