"""
Notification API Endpoints
User notification management and delivery
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import List, Optional
from datetime import datetime, timedelta
from app.core.database import get_session
from app.core.security import get_current_user
from app.models.user import User
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.schemas.notification import (
    NotificationCreate,
    NotificationResponse,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    BulkNotificationCreate
)
from uuid import UUID

router = APIRouter()


@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(
    unread_only: bool = Query(False, description="Filter for unread notifications only"),
    notification_type: Optional[NotificationType] = Query(None, description="Filter by notification type"),
    limit: int = Query(50, le=100, description="Number of notifications to retrieve"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Get user's notifications with optional filters"""
    query = select(Notification).where(Notification.user_id == current_user.id)

    if unread_only:
        query = query.where(Notification.status == NotificationStatus.PENDING)

    if notification_type:
        query = query.where(Notification.type == notification_type)

    query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    notifications = result.scalars().all()

    return [NotificationResponse.from_orm(n) for n in notifications]


@router.post("/mark-read/{notification_id}")
async def mark_notification_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Mark a notification as read"""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.user_id == current_user.id
            )
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )

    notification.status = NotificationStatus.SENT
    notification.sent_at = datetime.utcnow()
    await db.commit()

    return {"message": "Notification marked as read"}


@router.post("/mark-all-read")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Mark all user's notifications as read"""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.status == NotificationStatus.PENDING
            )
        )
    )
    notifications = result.scalars().all()

    for notification in notifications:
        notification.status = NotificationStatus.SENT
        notification.sent_at = datetime.utcnow()

    await db.commit()

    return {"message": f"Marked {len(notifications)} notifications as read"}


@router.get("/preferences", response_model=NotificationPreferences)
async def get_notification_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Get user's notification preferences"""
    # In a real implementation, these would be stored in the database
    # For now, return default preferences
    return NotificationPreferences(
        email_enabled=True,
        sms_enabled=False,
        push_enabled=True,
        event_reminders=True,
        booking_confirmations=True,
        payment_receipts=True,
        marketing_updates=False
    )


@router.put("/preferences", response_model=NotificationPreferences)
async def update_notification_preferences(
    preferences: NotificationPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Update user's notification preferences"""
    # In a real implementation, these would be stored in the database
    # For now, return updated preferences
    current_prefs = NotificationPreferences()

    # Update only provided fields
    update_data = preferences.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_prefs, field, value)

    return current_prefs


@router.post("/send", response_model=NotificationResponse)
async def send_notification(
    notification_data: NotificationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Send a notification (admin only)"""
    # Check if user is admin
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can send notifications"
        )

    # Create notification
    notification = Notification(
        user_id=notification_data.user_id,
        type=notification_data.type,
        content=notification_data.content,
        status=NotificationStatus.PENDING
    )

    db.add(notification)
    await db.commit()
    await db.refresh(notification)

    # In a real implementation, this would trigger actual notification delivery
    # For now, we'll just mark it as sent
    notification.status = NotificationStatus.SENT
    notification.sent_at = datetime.utcnow()
    await db.commit()
    await db.refresh(notification)

    return NotificationResponse.from_orm(notification)


@router.post("/send-bulk")
async def send_bulk_notifications(
    bulk_data: BulkNotificationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Send notifications to multiple users (admin only)"""
    # Check if user is admin
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can send bulk notifications"
        )

    notifications = []
    for user_id in bulk_data.user_ids:
        notification = Notification(
            user_id=user_id,
            type=bulk_data.type,
            content=bulk_data.content,
            status=NotificationStatus.PENDING
        )
        notifications.append(notification)
        db.add(notification)

    await db.commit()

    # If send_immediately is true, mark all as sent
    if bulk_data.send_immediately:
        for notification in notifications:
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.utcnow()
        await db.commit()

    return {
        "message": f"Created {len(notifications)} notifications",
        "status": "sent" if bulk_data.send_immediately else "queued"
    }


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Delete a notification"""
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.user_id == current_user.id
            )
        )
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )

    await db.delete(notification)
    await db.commit()

    return {"message": "Notification deleted successfully"}


@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Get count of unread notifications"""
    from sqlalchemy import func

    result = await db.execute(
        select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.status == NotificationStatus.PENDING
            )
        )
    )
    count = result.scalar()

    return {"unread_count": count}