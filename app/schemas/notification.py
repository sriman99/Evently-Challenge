"""
Notification schemas for request/response models
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import uuid
import enum


class NotificationType(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class NotificationCreate(BaseModel):
    user_id: uuid.UUID
    type: NotificationType
    content: str = Field(..., min_length=1, max_length=5000)


class NotificationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: NotificationType
    content: str
    status: NotificationStatus
    sent_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationPreferences(BaseModel):
    email_enabled: bool = True
    sms_enabled: bool = False
    push_enabled: bool = True
    event_reminders: bool = True
    booking_confirmations: bool = True
    payment_receipts: bool = True
    marketing_updates: bool = False


class NotificationPreferencesUpdate(BaseModel):
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    event_reminders: Optional[bool] = None
    booking_confirmations: Optional[bool] = None
    payment_receipts: Optional[bool] = None
    marketing_updates: Optional[bool] = None


class BulkNotificationCreate(BaseModel):
    user_ids: List[uuid.UUID]
    type: NotificationType
    content: str = Field(..., min_length=1, max_length=5000)
    send_immediately: bool = False