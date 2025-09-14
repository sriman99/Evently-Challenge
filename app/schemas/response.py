"""
Generic response schemas
"""

from pydantic import BaseModel, Field
from typing import Any, Optional, Dict, List, Generic, TypeVar
from datetime import datetime

T = TypeVar('T')


class SuccessResponse(BaseModel, Generic[T]):
    """Generic success response"""
    success: bool = True
    data: T
    message: str = "Operation successful"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorDetail(BaseModel):
    """Error detail schema"""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = {}


class ErrorResponse(BaseModel):
    """Generic error response"""
    success: bool = False
    error: ErrorDetail
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaginationMeta(BaseModel):
    """Pagination metadata"""
    page: int = Field(..., ge=1)
    per_page: int = Field(..., ge=1, le=100)
    total: int = Field(..., ge=0)
    total_pages: int = Field(..., ge=0)
    has_next: bool = False
    has_prev: bool = False


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response"""
    success: bool = True
    data: List[T]
    pagination: PaginationMeta
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: Optional[Dict[str, str]] = None


class MessageResponse(BaseModel):
    """Simple message response"""
    success: bool = True
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)