"""
Custom application exceptions
"""

from typing import Optional, Dict, Any


class EventlyException(Exception):
    """Base exception for Evently application"""

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(EventlyException):
    """Authentication related errors"""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="AUTH_ERROR",
            status_code=401,
            details=details
        )


class AuthorizationError(EventlyException):
    """Authorization related errors"""

    def __init__(self, message: str = "Not authorized", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="AUTH_FORBIDDEN",
            status_code=403,
            details=details
        )


class NotFoundError(EventlyException):
    """Resource not found errors"""

    def __init__(self, resource: str, identifier: Any = None):
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} with id {identifier} not found"
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=404
        )


class ValidationError(EventlyException):
    """Validation errors"""

    def __init__(self, message: str, field: Optional[str] = None):
        details = {"field": field} if field else {}
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=400,
            details=details
        )


class ConflictError(EventlyException):
    """Resource conflict errors"""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=409,
            details=details
        )


class BookingError(EventlyException):
    """Booking related errors"""

    def __init__(self, message: str, code: str = "BOOKING_ERROR", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code=code,
            status_code=400,
            details=details
        )


class SeatUnavailableError(BookingError):
    """Seat unavailable error"""

    def __init__(self, seat_ids: list = None):
        details = {"unavailable_seats": seat_ids} if seat_ids else {}
        super().__init__(
            message="Selected seats are no longer available",
            code="SEATS_UNAVAILABLE",
            details=details
        )


class BookingExpiredError(BookingError):
    """Booking expired error"""

    def __init__(self, booking_id: str):
        super().__init__(
            message="Booking has expired",
            code="BOOKING_EXPIRED",
            details={"booking_id": booking_id}
        )


class PaymentError(EventlyException):
    """Payment related errors"""

    def __init__(self, message: str = "Payment processing failed", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="PAYMENT_FAILED",
            status_code=402,
            details=details
        )


class RateLimitError(EventlyException):
    """Rate limit exceeded error"""

    def __init__(self, limit: int, window: int):
        super().__init__(
            message=f"Rate limit exceeded. Max {limit} requests per {window} seconds",
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"limit": limit, "window": window}
        )


class ConcurrencyError(EventlyException):
    """Concurrency conflict error"""

    def __init__(self, message: str = "Resource was modified by another process"):
        super().__init__(
            message=message,
            code="CONCURRENCY_ERROR",
            status_code=409
        )


class LockAcquisitionError(EventlyException):
    """Failed to acquire lock error"""

    def __init__(self, resource: str):
        super().__init__(
            message=f"Failed to acquire lock for resource: {resource}",
            code="LOCK_FAILED",
            status_code=409,
            details={"resource": resource}
        )


class ExternalServiceError(EventlyException):
    """External service error"""

    def __init__(self, service: str, message: str = None):
        super().__init__(
            message=message or f"External service {service} is unavailable",
            code="EXTERNAL_SERVICE_ERROR",
            status_code=503,
            details={"service": service}
        )