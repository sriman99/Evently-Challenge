"""
Payment schemas for request/response models
"""

from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field
import uuid
import enum


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentMethod(str, enum.Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    STRIPE = "stripe"
    BANK_TRANSFER = "bank_transfer"


class PaymentCreate(BaseModel):
    booking_id: uuid.UUID
    amount: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    payment_method_id: str
    return_url: Optional[str] = None


class PaymentIntentResponse(BaseModel):
    payment_intent_id: str
    client_secret: str
    amount: Decimal
    currency: str = "USD"
    status: str


class PaymentResponse(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    amount: Decimal
    currency: str
    status: PaymentStatus
    payment_method: Optional[PaymentMethod]
    gateway_reference: Optional[str]
    processed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class RefundRequest(BaseModel):
    amount: Optional[Decimal] = Field(None, gt=0, max_digits=10, decimal_places=2)
    reason: str = Field(..., min_length=1, max_length=500)


class RefundResponse(BaseModel):
    payment_id: uuid.UUID
    refund_id: str
    amount: Decimal
    status: str
    reason: str
    refunded_at: datetime


class PaymentWebhook(BaseModel):
    event_type: str
    payment_intent_id: str
    status: str
    metadata: Dict[str, Any]