"""
Production monitoring and metrics for booking system
"""

import time
import logging
from typing import Dict, Optional
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class BookingMetrics:
    """Booking system metrics"""
    total_bookings: int = 0
    successful_bookings: int = 0
    failed_bookings: int = 0
    cancelled_bookings: int = 0
    confirmed_bookings: int = 0
    expired_bookings: int = 0

    # Performance metrics
    avg_booking_time: float = 0.0
    max_booking_time: float = 0.0
    min_booking_time: float = float('inf')

    # Concurrency metrics
    concurrent_bookings: int = 0
    max_concurrent_bookings: int = 0
    redis_failures: int = 0
    database_failures: int = 0

    # Rate limiting metrics
    rate_limited_requests: int = 0

    # Circuit breaker metrics
    circuit_breaker_open_count: int = 0

    # Booking times for percentile calculation
    booking_times: list = field(default_factory=list)

    def add_booking_time(self, duration: float):
        """Add booking duration for metrics"""
        self.booking_times.append(duration)
        if len(self.booking_times) > 1000:  # Keep only last 1000 for memory
            self.booking_times = self.booking_times[-1000:]

        # Update basic stats
        if duration < self.min_booking_time:
            self.min_booking_time = duration
        if duration > self.max_booking_time:
            self.max_booking_time = duration

        # Update average
        if self.booking_times:
            self.avg_booking_time = sum(self.booking_times) / len(self.booking_times)

    def get_percentiles(self) -> Dict[str, float]:
        """Calculate booking time percentiles"""
        if not self.booking_times:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        sorted_times = sorted(self.booking_times)
        length = len(sorted_times)

        return {
            "p50": sorted_times[int(length * 0.5)] if length > 0 else 0.0,
            "p95": sorted_times[int(length * 0.95)] if length > 0 else 0.0,
            "p99": sorted_times[int(length * 0.99)] if length > 0 else 0.0,
        }

    def get_success_rate(self) -> float:
        """Calculate booking success rate"""
        if self.total_bookings == 0:
            return 0.0
        return (self.successful_bookings / self.total_bookings) * 100

    def to_dict(self) -> Dict:
        """Convert metrics to dictionary"""
        percentiles = self.get_percentiles()

        return {
            "total_bookings": self.total_bookings,
            "successful_bookings": self.successful_bookings,
            "failed_bookings": self.failed_bookings,
            "cancelled_bookings": self.cancelled_bookings,
            "confirmed_bookings": self.confirmed_bookings,
            "expired_bookings": self.expired_bookings,
            "success_rate_percent": self.get_success_rate(),
            "performance": {
                "avg_booking_time_ms": self.avg_booking_time * 1000,
                "max_booking_time_ms": self.max_booking_time * 1000,
                "min_booking_time_ms": self.min_booking_time * 1000 if self.min_booking_time != float('inf') else 0,
                "percentiles_ms": {
                    "p50": percentiles["p50"] * 1000,
                    "p95": percentiles["p95"] * 1000,
                    "p99": percentiles["p99"] * 1000,
                }
            },
            "concurrency": {
                "current_concurrent_bookings": self.concurrent_bookings,
                "max_concurrent_bookings": self.max_concurrent_bookings,
                "redis_failures": self.redis_failures,
                "database_failures": self.database_failures,
            },
            "rate_limiting": {
                "rate_limited_requests": self.rate_limited_requests,
            },
            "circuit_breaker": {
                "open_count": self.circuit_breaker_open_count,
            }
        }


class MetricsCollector:
    """Production metrics collector for booking system"""

    def __init__(self):
        self.metrics = BookingMetrics()
        self.logger = logging.getLogger(__name__)
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def track_booking_operation(self, operation_type: str = "booking"):
        """Context manager to track booking operation metrics"""
        start_time = time.time()

        async with self._lock:
            self.metrics.concurrent_bookings += 1
            if self.metrics.concurrent_bookings > self.metrics.max_concurrent_bookings:
                self.metrics.max_concurrent_bookings = self.metrics.concurrent_bookings

        try:
            yield
            # Success
            end_time = time.time()
            duration = end_time - start_time

            async with self._lock:
                self.metrics.total_bookings += 1
                self.metrics.successful_bookings += 1
                self.metrics.add_booking_time(duration)
                self.metrics.concurrent_bookings -= 1

            if duration > 5.0:  # Log slow operations
                self.logger.warning(f"Slow {operation_type} operation: {duration:.2f}s")

        except Exception as e:
            # Failure
            end_time = time.time()
            duration = end_time - start_time
            error_type = None

            # Classify error type first
            if "redis" in str(e).lower() or "circuit breaker" in str(e).lower():
                error_type = "redis"
            elif "database" in str(e).lower() or "sqlalchemy" in str(e).lower():
                error_type = "database"

            # Single lock acquisition for all failure metrics
            async with self._lock:
                self.metrics.total_bookings += 1
                self.metrics.failed_bookings += 1
                self.metrics.add_booking_time(duration)
                self.metrics.concurrent_bookings -= 1

                # Update error-specific counters
                if error_type == "redis":
                    self.metrics.redis_failures += 1
                elif error_type == "database":
                    self.metrics.database_failures += 1

            self.logger.error(f"Failed {operation_type} operation: {e} (duration: {duration:.2f}s)")
            raise

    async def record_booking_status_change(self, from_status: str, to_status: str):
        """Record booking status changes"""
        async with self._lock:
            if to_status == "confirmed":
                self.metrics.confirmed_bookings += 1
            elif to_status == "cancelled":
                self.metrics.cancelled_bookings += 1
            elif to_status == "expired":
                self.metrics.expired_bookings += 1

    async def record_rate_limit_hit(self):
        """Record rate limit hit"""
        async with self._lock:
            self.metrics.rate_limited_requests += 1

    async def record_circuit_breaker_open(self):
        """Record circuit breaker opening"""
        async with self._lock:
            self.metrics.circuit_breaker_open_count += 1

    async def get_metrics(self) -> Dict:
        """Get current metrics"""
        async with self._lock:
            return self.metrics.to_dict()

    async def reset_metrics(self):
        """Reset all metrics (useful for testing)"""
        async with self._lock:
            self.metrics = BookingMetrics()
            self.logger.info("Metrics reset")

    async def log_metrics_summary(self):
        """Log metrics summary"""
        metrics_dict = await self.get_metrics()

        self.logger.info(f"""
Booking System Metrics Summary:
================================
Total Bookings: {metrics_dict['total_bookings']}
Success Rate: {metrics_dict['success_rate_percent']:.2f}%
Successful: {metrics_dict['successful_bookings']}
Failed: {metrics_dict['failed_bookings']}
Confirmed: {metrics_dict['confirmed_bookings']}
Cancelled: {metrics_dict['cancelled_bookings']}
Expired: {metrics_dict['expired_bookings']}

Performance:
- Avg Time: {metrics_dict['performance']['avg_booking_time_ms']:.1f}ms
- P50: {metrics_dict['performance']['percentiles_ms']['p50']:.1f}ms
- P95: {metrics_dict['performance']['percentiles_ms']['p95']:.1f}ms
- P99: {metrics_dict['performance']['percentiles_ms']['p99']:.1f}ms

Concurrency:
- Current Concurrent: {metrics_dict['concurrency']['current_concurrent_bookings']}
- Max Concurrent: {metrics_dict['concurrency']['max_concurrent_bookings']}
- Redis Failures: {metrics_dict['concurrency']['redis_failures']}
- DB Failures: {metrics_dict['concurrency']['database_failures']}

Rate Limiting:
- Rate Limited Requests: {metrics_dict['rate_limiting']['rate_limited_requests']}

Circuit Breaker:
- Times Opened: {metrics_dict['circuit_breaker']['open_count']}
        """.strip())


class HealthChecker:
    """Health checking for booking system components"""

    def __init__(self, redis_manager, db_manager):
        self.redis_manager = redis_manager
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)

    async def check_redis_health(self) -> Dict[str, any]:
        """Check Redis health"""
        try:
            start_time = time.time()
            client = await self.redis_manager.get_client()
            await client.ping()
            response_time = time.time() - start_time

            return {
                "status": "healthy",
                "response_time_ms": response_time * 1000,
                "error": None
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "response_time_ms": None,
                "error": str(e)
            }

    async def check_database_health(self) -> Dict[str, any]:
        """Check database health"""
        try:
            start_time = time.time()

            # Simple connectivity test
            async with self.db_manager.session_factory() as session:
                await session.execute(text("SELECT 1"))

            response_time = time.time() - start_time

            return {
                "status": "healthy",
                "response_time_ms": response_time * 1000,
                "error": None
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "response_time_ms": None,
                "error": str(e)
            }

    async def get_system_health(self) -> Dict[str, any]:
        """Get overall system health"""
        redis_health = await self.check_redis_health()
        db_health = await self.check_database_health()

        overall_status = "healthy"
        if redis_health["status"] != "healthy" or db_health["status"] != "healthy":
            overall_status = "degraded" if redis_health["status"] == "healthy" or db_health["status"] == "healthy" else "unhealthy"

        return {
            "status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {
                "redis": redis_health,
                "database": db_health
            }
        }


# Global instances
metrics_collector = MetricsCollector()


# Monitoring API endpoints (to be added to FastAPI app)
async def get_metrics():
    """API endpoint to get metrics"""
    return await metrics_collector.get_metrics()


async def get_health():
    """API endpoint to get health status"""
    from app.core.redis import redis_manager
    from app.core.database import db_manager

    health_checker = HealthChecker(redis_manager, db_manager)
    return await health_checker.get_system_health()


# Background task for periodic metrics logging
async def start_metrics_logging_task():
    """Start background task for periodic metrics logging"""
    async def log_metrics_periodically():
        while True:
            try:
                await asyncio.sleep(300)  # Log every 5 minutes
                await metrics_collector.log_metrics_summary()
            except Exception as e:
                logger.error(f"Error in metrics logging task: {e}")

    asyncio.create_task(log_metrics_periodically())