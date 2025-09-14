"""
Main API Router
Aggregates all API endpoints for v1
"""

from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    users,
    events,
    bookings,
    venues,
    seats,
    payment,
    notifications,
    admin,
    health
)

api_router = APIRouter()

# Include all routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(venues.router, prefix="/venues", tags=["venues"])
api_router.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
api_router.include_router(seats.router, prefix="/seats", tags=["seats"])
api_router.include_router(payment.router, prefix="/payments", tags=["payments"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(health.router, prefix="/health", tags=["health"])