"""
Transaction model
"""

from sqlalchemy import Column, String, ForeignKey, Enum, Numeric, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.models.base import BaseModel


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class Transaction(BaseModel):
    """
    Transaction model for payment records
    """
    __tablename__ = "transactions"

    booking_id = Column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(
        Enum(TransactionStatus),
        default=TransactionStatus.PENDING,
        nullable=False,
        index=True
    )
    payment_method = Column(String(50))
    gateway_reference = Column(String(255))
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    booking = relationship("Booking", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction(id={self.id}, booking_id={self.booking_id}, amount={self.amount}, status={self.status})>"