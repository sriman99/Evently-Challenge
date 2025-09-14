"""
Payment API Endpoints
Core payment processing endpoints required for booking system
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_session
from app.core.security import get_current_user
from app.models.user import User
from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import (
    PaymentCreate,
    PaymentResponse,
    PaymentIntentResponse,
    RefundRequest,
    RefundResponse
)
from uuid import UUID

router = APIRouter()


@router.post("/intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    booking_id: UUID,
    amount: float,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Create payment intent for booking"""
    import secrets

    # Create mock payment intent (in production, this would call Stripe API)
    payment_intent = {
        "payment_intent_id": f"pi_{secrets.token_hex(16)}",
        "client_secret": f"pi_{secrets.token_hex(16)}_secret_{secrets.token_hex(24)}",
        "amount": amount,
        "currency": "USD",
        "status": "requires_payment_method"
    }

    return PaymentIntentResponse(**payment_intent)


@router.post("/process", response_model=PaymentResponse)
async def process_payment(
    payment_data: PaymentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Process payment for booking"""
    from datetime import datetime
    import secrets

    # Create payment record
    payment = Payment(
        booking_id=payment_data.booking_id,
        amount=payment_data.amount,
        currency="USD",
        status=PaymentStatus.COMPLETED,
        gateway_reference=f"ch_{secrets.token_hex(16)}",
        payment_intent_id=payment_data.payment_method_id,
        processed_at=datetime.utcnow()
    )

    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    return payment


@router.post("/refund/{payment_id}", response_model=RefundResponse)
async def refund_payment(
    payment_id: UUID,
    refund_request: RefundRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Process refund for payment"""
    from sqlalchemy import select
    from datetime import datetime
    import secrets

    # Get the payment
    result = await db.execute(
        select(Payment).where(Payment.id == payment_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )

    # Check if already refunded
    if payment.status in [PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment already refunded"
        )

    # Process refund (mock implementation)
    refund_amount = refund_request.amount or payment.amount

    if refund_amount > payment.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refund amount exceeds payment amount"
        )

    # Update payment record
    payment.refund_amount = refund_amount
    payment.refund_reason = refund_request.reason
    payment.refunded_at = datetime.utcnow()

    if refund_amount == payment.amount:
        payment.status = PaymentStatus.REFUNDED
    else:
        payment.status = PaymentStatus.PARTIALLY_REFUNDED

    await db.commit()
    await db.refresh(payment)

    return RefundResponse(
        payment_id=payment.id,
        refund_id=f"refund_{secrets.token_hex(16)}",
        amount=refund_amount,
        status="completed",
        reason=refund_request.reason,
        refunded_at=payment.refunded_at
    )


@router.get("/history", response_model=List[PaymentResponse])
async def get_payment_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Get user's payment history"""
    from sqlalchemy import select
    from app.models.booking import Booking

    # Get all payments for user's bookings
    result = await db.execute(
        select(Payment)
        .join(Booking, Payment.booking_id == Booking.id)
        .where(Booking.user_id == current_user.id)
        .order_by(Payment.created_at.desc())
    )
    payments = result.scalars().all()

    return [PaymentResponse.from_orm(payment) for payment in payments]