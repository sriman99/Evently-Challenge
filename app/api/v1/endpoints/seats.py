"""
Seat management endpoints
"""

from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.core.database import get_session
from app.core.redis import get_redis
from app.core.security import get_current_user
from app.models.user import User
from app.models.seat import Seat, SeatStatus
from app.schemas.seat import SeatResponse

router = APIRouter()


@router.post("/reserve")
async def reserve_seats(
    event_id: str,
    seat_ids: List[str],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    redis_client = Depends(get_redis)
) -> Any:
    """
    Temporarily reserve seats (for seat selection UI)
    """
    reserved_seats = []

    for seat_id in seat_ids:
        # Set temporary reservation in Redis (5 minutes)
        lock_key = f"seat_reserve:{event_id}:{seat_id}"
        acquired = await redis_client.set(
            lock_key,
            str(current_user.id),
            nx=True,
            ex=300  # 5 minutes
        )

        if acquired:
            reserved_seats.append(seat_id)

    return {
        "status": "reserved",
        "seat_ids": reserved_seats,
        "expires_in": 300
    }


@router.post("/release")
async def release_seats(
    event_id: str,
    seat_ids: List[str],
    current_user: User = Depends(get_current_user),
    redis_client = Depends(get_redis)
) -> Any:
    """
    Release temporarily reserved seats
    """
    for seat_id in seat_ids:
        lock_key = f"seat_reserve:{event_id}:{seat_id}"
        await redis_client.delete(lock_key)

    return {
        "status": "released",
        "seat_ids": seat_ids
    }