"""
Monitoring and health check endpoints for production system
"""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
import logging

from app.core.metrics import metrics_collector, get_health
from app.core.redis import redis_manager
from app.core.database import db_manager

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()


@router.get("/health")
async def health_check() -> Any:
    """
    System health check endpoint
    Returns overall health status of all components
    """
    try:
        health_status = await get_health()

        # Return appropriate HTTP status based on health
        if health_status["status"] == "unhealthy":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=health_status
            )
        elif health_status["status"] == "degraded":
            # Return 200 but indicate degraded status
            return {**health_status, "warning": "System is running in degraded mode"}

        return health_status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Health check system error"
        )


@router.get("/health/redis")
async def redis_health() -> Any:
    """
    Redis-specific health check
    """
    try:
        client = await redis_manager.get_client()
        await client.ping()

        return {
            "status": "healthy",
            "service": "redis",
            "message": "Redis is responding normally"
        }

    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "service": "redis",
                "error": str(e)
            }
        )


@router.get("/health/database")
async def database_health() -> Any:
    """
    Database-specific health check
    """
    try:
        async with db_manager.session_factory() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "service": "database",
            "message": "Database is responding normally"
        }

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "service": "database",
                "error": str(e)
            }
        )


@router.get("/metrics")
async def get_system_metrics() -> Any:
    """
    Get comprehensive system metrics
    Requires authentication in production
    """
    try:
        metrics = await metrics_collector.get_metrics()
        return {
            "timestamp": metrics_collector.metrics.to_dict().get("timestamp"),
            "booking_system": metrics
        }

    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve metrics"
        )


@router.get("/metrics/summary")
async def get_metrics_summary() -> Any:
    """
    Get high-level metrics summary
    """
    try:
        metrics = await metrics_collector.get_metrics()

        return {
            "system_status": "operational" if metrics["success_rate_percent"] > 95 else "degraded",
            "total_bookings": metrics["total_bookings"],
            "success_rate": f"{metrics['success_rate_percent']:.1f}%",
            "avg_response_time": f"{metrics['performance']['avg_booking_time_ms']:.0f}ms",
            "current_load": metrics["concurrency"]["current_concurrent_bookings"],
            "errors": {
                "redis_failures": metrics["concurrency"]["redis_failures"],
                "database_failures": metrics["concurrency"]["database_failures"],
                "rate_limited": metrics["rate_limiting"]["rate_limited_requests"]
            }
        }

    except Exception as e:
        logger.error(f"Failed to get metrics summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve metrics summary"
        )


@router.get("/metrics/performance")
async def get_performance_metrics() -> Any:
    """
    Get detailed performance metrics
    """
    try:
        metrics = await metrics_collector.get_metrics()

        return {
            "response_times": metrics["performance"],
            "concurrency": metrics["concurrency"],
            "throughput": {
                "successful_bookings": metrics["successful_bookings"],
                "failed_bookings": metrics["failed_bookings"],
                "success_rate": metrics["success_rate_percent"]
            }
        }

    except Exception as e:
        logger.error(f"Failed to get performance metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve performance metrics"
        )


@router.post("/metrics/reset")
async def reset_metrics(token: str = Depends(security)) -> Any:
    """
    Reset all metrics (admin only)
    USE WITH CAUTION - This clears all collected metrics
    """
    try:
        await metrics_collector.reset_metrics()
        logger.info("Metrics reset by admin request")

        return {
            "message": "Metrics have been reset successfully",
            "warning": "All historical metrics data has been cleared"
        }

    except Exception as e:
        logger.error(f"Failed to reset metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to reset metrics"
        )


@router.get("/status")
async def system_status() -> Any:
    """
    Quick system status check
    Lightweight endpoint for load balancers
    """
    return {
        "status": "ok",
        "service": "evently-booking-system",
        "version": "1.0.0"
    }


@router.get("/redis/info")
async def redis_info() -> Any:
    """
    Redis connection and performance info
    """
    try:
        client = await redis_manager.get_client()

        # Get Redis info
        info = await client.info()

        # Extract key metrics
        return {
            "connected_clients": info.get("connected_clients"),
            "used_memory_human": info.get("used_memory_human"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
            "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec"),
            "redis_version": info.get("redis_version")
        }

    except Exception as e:
        logger.error(f"Failed to get Redis info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve Redis information"
        )


@router.get("/database/info")
async def database_info() -> Any:
    """
    Database connection and performance info
    """
    try:
        pool_info = {
            "pool_size": db_manager.session_factory.bind.pool.size(),
            "checked_out": db_manager.session_factory.bind.pool.checkedout(),
            "checked_in": db_manager.session_factory.bind.pool.checkedin(),
            "invalid": db_manager.session_factory.bind.pool.invalid(),
        }

        return {
            "connection_pool": pool_info,
            "engine_info": {
                "dialect": str(db_manager.session_factory.bind.dialect),
                "driver": db_manager.session_factory.bind.dialect.driver
            }
        }

    except Exception as e:
        logger.error(f"Failed to get database info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve database information"
        )