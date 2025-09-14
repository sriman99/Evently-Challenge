"""
Health check endpoints
"""

from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_session
from app.core.redis import get_redis
from app.config import settings

router = APIRouter()


@router.get("/live")
async def liveness() -> Any:
    """
    Kubernetes liveness probe
    """
    return {"status": "alive", "service": "evently-api"}


@router.get("/ready")
async def readiness(
    db: AsyncSession = Depends(get_session),
    redis_client = Depends(get_redis)
) -> Any:
    """
    Kubernetes readiness probe - checks all dependencies
    """
    checks = {
        "database": False,
        "redis": False,
        "api": True
    }

    # Check database
    try:
        result = await db.execute(text("SELECT 1"))
        checks["database"] = result.scalar() == 1
    except Exception:
        pass

    # Check Redis
    try:
        await redis_client.ping()
        checks["redis"] = True
    except Exception:
        pass

    # Overall status
    all_healthy = all(checks.values())

    return {
        "status": "ready" if all_healthy else "not ready",
        "checks": checks,
        "version": settings.APP_VERSION
    }


@router.get("/status")
async def system_status(
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Get system status and metrics
    """
    from app.models.event import Event
    from app.models.booking import Booking
    from app.models.user import User
    from sqlalchemy import func

    # Get counts
    events_count = await db.execute(func.count(Event.id))
    bookings_count = await db.execute(func.count(Booking.id))
    users_count = await db.execute(func.count(User.id))

    return {
        "status": "operational",
        "environment": settings.APP_ENV,
        "version": settings.APP_VERSION,
        "statistics": {
            "total_events": events_count.scalar() or 0,
            "total_bookings": bookings_count.scalar() or 0,
            "total_users": users_count.scalar() or 0
        }
    }