"""
Main FastAPI application
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import logging
import time
from prometheus_client import make_asgi_app, Counter, Histogram
import uuid

from app.config import settings
from app.core.database import init_db, close_db
from app.core.redis import init_redis, close_redis
from app.core.logging import setup_logging
from app.api.v1.endpoints import auth, users, events, bookings, admin, websocket, payment, notifications, venues, seats, health

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Prometheus metrics - use try/except to avoid duplicate registration
try:
    REQUEST_COUNT = Counter(
        "app_requests_total",
        "Total requests",
        ["method", "endpoint", "status"]
    )
    REQUEST_DURATION = Histogram(
        "app_request_duration_seconds",
        "Request duration",
        ["method", "endpoint"]
    )
except ValueError:
    # Metrics already registered, get them from registry
    from prometheus_client import REGISTRY
    REQUEST_COUNT = REGISTRY._names_to_collectors["app_requests_total"]
    REQUEST_DURATION = REGISTRY._names_to_collectors["app_request_duration_seconds"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    """
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Initialize database
    await init_db()
    logger.info("Database connection established")

    # Initialize Redis
    await init_redis()
    logger.info("Redis connection established")

    # Initialize RabbitMQ (if needed)
    # await init_rabbitmq()

    yield

    # Shutdown
    logger.info("Shutting down application")

    # Close database connections
    await close_db()
    logger.info("Database connections closed")

    # Close Redis connections
    await close_redis()
    logger.info("Redis connections closed")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Scalable Event Ticketing Platform",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Trusted Host middleware (security)
if settings.is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*.evently.com", "evently.com","*"]
    )


# Request tracking middleware
@app.middleware("http")
async def track_requests(request: Request, call_next):
    """
    Track request metrics and add request ID
    """
    # Generate request ID
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    # Track request timing
    start_time = time.time()

    # Add request ID to response headers
    response = await call_next(request)

    # Calculate request duration
    duration = time.time() - start_time

    # Record metrics
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()

    REQUEST_DURATION.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)

    # Add headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = str(duration)

    return response


# Exception handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": "The requested resource was not found"
            }
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error(f"Internal server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal server error occurred"
            }
        }
    )


# Health check endpoints
@app.get("/health/live")
async def liveness():
    """Kubernetes liveness probe"""
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    """Kubernetes readiness probe"""
    # Check database connection
    # Check Redis connection
    return {"status": "ready"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "api_docs": "/docs" if settings.DEBUG else None
    }


# Include routers
app.include_router(
    auth.router,
    prefix=f"{settings.API_PREFIX}/auth",
    tags=["Authentication"]
)

app.include_router(
    users.router,
    prefix=f"{settings.API_PREFIX}/users",
    tags=["Users"]
)

app.include_router(
    events.router,
    prefix=f"{settings.API_PREFIX}/events",
    tags=["Events"]
)

app.include_router(
    bookings.router,
    prefix=f"{settings.API_PREFIX}/bookings",
    tags=["Bookings"]
)

app.include_router(
    admin.router,
    prefix=f"{settings.API_PREFIX}/admin",
    tags=["Admin"]
)

# WebSocket endpoint
app.include_router(
    websocket.router,
    prefix="/ws",
    tags=["WebSocket"]
)

# Payment endpoints
app.include_router(
    payment.router,
    prefix=f"{settings.API_PREFIX}/payments",
    tags=["Payments"]
)

# Notification endpoints
app.include_router(
    notifications.router,
    prefix=f"{settings.API_PREFIX}/notifications",
    tags=["Notifications"]
)

# Venue endpoints
app.include_router(
    venues.router,
    prefix=f"{settings.API_PREFIX}/venues",
    tags=["Venues"]
)

# Seat endpoints
app.include_router(
    seats.router,
    prefix=f"{settings.API_PREFIX}/seats",
    tags=["Seats"]
)

# Health endpoints
app.include_router(
    health.router,
    prefix=f"{settings.API_PREFIX}/health",
    tags=["Health"]
)

# Mount Prometheus metrics endpoint
if settings.PROMETHEUS_ENABLED:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )