"""
Venue management endpoints
"""

from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.models.venue import Venue
from app.schemas.venue import VenueResponse, VenueDetail

router = APIRouter()


@router.get("/", response_model=List[VenueResponse])
async def get_venues(
    db: AsyncSession = Depends(get_session),
    skip: int = 0,
    limit: int = 100
) -> Any:
    """
    Get list of all venues
    """
    stmt = (
        select(Venue)
        .offset(skip)
        .limit(limit)
        .order_by(Venue.name)
    )

    result = await db.execute(stmt)
    venues = result.scalars().all()

    return venues


@router.get("/{venue_id}", response_model=VenueDetail)
async def get_venue(
    venue_id: str,
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Get detailed information about a specific venue
    """
    stmt = (
        select(Venue)
        .options(selectinload(Venue.events))
        .where(Venue.id == venue_id)
    )

    result = await db.execute(stmt)
    venue = result.scalar_one_or_none()

    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found"
        )

    return venue