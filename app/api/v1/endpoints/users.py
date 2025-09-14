"""
User management endpoints
"""

from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.database import get_session
from app.core.security import get_current_user, get_password_hash
from app.models.user import User
from app.models.booking import Booking
from app.schemas.user import UserResponse, UserUpdate, PasswordChange
from app.schemas.booking import BookingResponse

router = APIRouter()


@router.get("/profile", response_model=UserResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get current user profile
    """
    return current_user


@router.put("/profile", response_model=UserResponse)
async def update_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Update current user profile
    """
    # Update user fields
    update_data = user_update.dict(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return current_user


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Change user password
    """
    from app.core.security import verify_password

    # Verify current password
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )

    # Update password
    current_user.password_hash = get_password_hash(password_data.new_password)

    await db.commit()

    return {"message": "Password updated successfully"}


@router.get("/bookings", response_model=List[BookingResponse])
async def get_user_bookings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    skip: int = 0,
    limit: int = 100
) -> Any:
    """
    Get current user's booking history
    """
    stmt = (
        select(Booking)
        .where(Booking.user_id == current_user.id)
        .order_by(Booking.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(stmt)
    bookings = result.scalars().all()

    return bookings


@router.delete("/account")
async def delete_user_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Delete user account (soft delete)
    """
    # Soft delete - just deactivate the account
    current_user.is_active = False

    await db.commit()

    return {"message": "Account deactivated successfully"}