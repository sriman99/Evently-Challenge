"""
Payment model for transaction processing
"""

from sqlalchemy import Column, String, Numeric, Enum, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.models.base import BaseModel


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


class Payment(BaseModel):
    """
    Payment model for tracking transactions
    """
    __tablename__ = "payments"

    booking_id = Column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    status = Column(
        Enum(PaymentStatus),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True
    )
    payment_method = Column(
        Enum(PaymentMethod),
        nullable=True
    )
    gateway_reference = Column(String(255), unique=True)
    gateway_response = Column(String(500))

    # Payment intent for stripe
    payment_intent_id = Column(String(255))
    client_secret = Column(String(255))

    # Timestamps
    processed_at = Column(DateTime(timezone=True))
    failed_at = Column(DateTime(timezone=True))
    refunded_at = Column(DateTime(timezone=True))

    # Refund details
    refund_amount = Column(Numeric(10, 2))
    refund_reason = Column(String(500))

    # Relationships
    booking = relationship("Booking", back_populates="payments")

    def __repr__(self):
        return f"<Payment(id={self.id}, booking_id={self.booking_id}, amount={self.amount}, status={self.status})>"