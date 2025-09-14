"""
Notification model
"""

from sqlalchemy import Column, String, ForeignKey, Enum, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.models.base import BaseModel


class NotificationType(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class Notification(BaseModel):
    """
    Notification model for user communications
    """
    __tablename__ = "notifications"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    type = Column(
        Enum(NotificationType),
        nullable=False,
        index=True
    )
    content = Column(Text, nullable=False)
    status = Column(
        Enum(NotificationStatus),
        default=NotificationStatus.PENDING,
        nullable=False,
        index=True
    )
    sent_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="notifications")

    def __repr__(self):
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.type}, status={self.status})>"