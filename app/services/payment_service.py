"""
Payment Service with Stripe Integration
Handles all payment processing for ticket bookings
"""

import stripe
from typing import Dict, Optional, Any
from decimal import Decimal
from datetime import datetime
import logging
from app.core.config import settings
from app.models.payment import Payment, PaymentStatus
from app.models.booking import Booking
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


class PaymentService:
    """Service for handling payment operations"""

    @staticmethod
    async def create_payment_intent(
        amount: Decimal,
        currency: str = "usd",
        metadata: Dict = None
    ) -> Dict:
        """Create a Stripe payment intent"""
        try:
            # Convert decimal to cents
            amount_cents = int(amount * 100)

            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency,
                payment_method_types=["card"],
                metadata=metadata or {}
            )

            return {
                "client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
                "amount": amount,
                "currency": currency
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error: {str(e)}")
            raise Exception(f"Payment processing error: {str(e)}")

    @staticmethod
    async def process_payment(
        db: AsyncSession,
        booking_id: str,
        payment_method_id: str,
        amount: Decimal
    ) -> Payment:
        """Process payment for a booking"""
        try:
            # Get booking
            booking = await db.get(Booking, booking_id)
            if not booking:
                raise ValueError("Booking not found")

            # Create payment intent
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),
                currency="usd",
                payment_method=payment_method_id,
                confirm=True,
                metadata={
                    "booking_id": booking_id,
                    "user_id": str(booking.user_id)
                }
            )

            # Create payment record
            payment = Payment(
                booking_id=booking_id,
                amount=amount,
                currency="USD",
                payment_method="stripe",
                transaction_id=intent.id,
                status=PaymentStatus.COMPLETED if intent.status == "succeeded" else PaymentStatus.PENDING,
                processed_at=datetime.utcnow() if intent.status == "succeeded" else None,
                gateway_response=intent.to_dict_recursive()
            )

            db.add(payment)

            # Update booking status if payment successful
            if intent.status == "succeeded":
                booking.status = "confirmed"
                booking.payment_status = "paid"

            await db.commit()
            await db.refresh(payment)

            return payment

        except stripe.error.CardError as e:
            # Handle card errors
            logger.error(f"Card error: {str(e)}")

            # Create failed payment record
            payment = Payment(
                booking_id=booking_id,
                amount=amount,
                currency="USD",
                payment_method="stripe",
                status=PaymentStatus.FAILED,
                gateway_response={"error": str(e)}
            )
            db.add(payment)
            await db.commit()

            raise Exception(f"Card declined: {str(e)}")

        except Exception as e:
            logger.error(f"Payment processing error: {str(e)}")
            raise

    @staticmethod
    async def refund_payment(
        db: AsyncSession,
        payment_id: str,
        amount: Optional[Decimal] = None,
        reason: str = "requested_by_customer"
    ) -> Dict:
        """Process refund for a payment"""
        try:
            # Get payment record
            payment = await db.get(Payment, payment_id)
            if not payment:
                raise ValueError("Payment not found")

            # Process refund with Stripe
            refund_amount = amount or payment.amount
            refund = stripe.Refund.create(
                payment_intent=payment.transaction_id,
                amount=int(refund_amount * 100) if amount else None,
                reason=reason
            )

            # Update payment record
            payment.status = PaymentStatus.REFUNDED
            payment.refunded_amount = refund_amount
            payment.refunded_at = datetime.utcnow()
            payment.gateway_response["refund"] = refund.to_dict_recursive()

            await db.commit()

            return {
                "refund_id": refund.id,
                "amount": refund_amount,
                "status": refund.status,
                "reason": reason
            }

        except stripe.error.StripeError as e:
            logger.error(f"Refund error: {str(e)}")
            raise Exception(f"Refund processing error: {str(e)}")

    @staticmethod
    async def verify_webhook(payload: bytes, signature: str) -> Dict:
        """Verify and process Stripe webhook"""
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, settings.STRIPE_WEBHOOK_SECRET
            )

            # Handle different event types
            if event.type == "payment_intent.succeeded":
                return await PaymentService._handle_payment_success(event.data.object)
            elif event.type == "payment_intent.payment_failed":
                return await PaymentService._handle_payment_failure(event.data.object)
            elif event.type == "charge.refunded":
                return await PaymentService._handle_refund(event.data.object)

            return {"status": "unhandled", "type": event.type}

        except stripe.error.SignatureVerificationError:
            logger.error("Invalid webhook signature")
            raise Exception("Invalid webhook signature")

    @staticmethod
    async def _handle_payment_success(payment_intent):
        """Handle successful payment webhook"""
        booking_id = payment_intent.metadata.get("booking_id")

        # Update booking and payment status
        # This would be implemented with database session
        logger.info(f"Payment successful for booking {booking_id}")

        return {
            "status": "success",
            "booking_id": booking_id,
            "amount": payment_intent.amount / 100
        }

    @staticmethod
    async def _handle_payment_failure(payment_intent):
        """Handle failed payment webhook"""
        booking_id = payment_intent.metadata.get("booking_id")

        logger.error(f"Payment failed for booking {booking_id}")

        return {
            "status": "failed",
            "booking_id": booking_id,
            "error": payment_intent.last_payment_error
        }

    @staticmethod
    async def _handle_refund(charge):
        """Handle refund webhook"""
        logger.info(f"Refund processed: {charge.id}")

        return {
            "status": "refunded",
            "charge_id": charge.id,
            "amount_refunded": charge.amount_refunded / 100
        }

    @staticmethod
    async def get_payment_methods(customer_id: str) -> list:
        """Get saved payment methods for a customer"""
        try:
            payment_methods = stripe.PaymentMethod.list(
                customer=customer_id,
                type="card"
            )

            return [
                {
                    "id": pm.id,
                    "brand": pm.card.brand,
                    "last4": pm.card.last4,
                    "exp_month": pm.card.exp_month,
                    "exp_year": pm.card.exp_year
                }
                for pm in payment_methods
            ]
        except stripe.error.StripeError as e:
            logger.error(f"Error fetching payment methods: {str(e)}")
            return []

    @staticmethod
    async def create_customer(user_email: str, user_id: str) -> str:
        """Create a Stripe customer"""
        try:
            customer = stripe.Customer.create(
                email=user_email,
                metadata={"user_id": user_id}
            )
            return customer.id
        except stripe.error.StripeError as e:
            logger.error(f"Error creating customer: {str(e)}")
            raise Exception(f"Customer creation error: {str(e)}")


class PaymentValidator:
    """Validator for payment-related operations"""

    @staticmethod
    def validate_card_number(card_number: str) -> bool:
        """Validate credit card number using Luhn algorithm"""
        if not card_number.isdigit():
            return False

        digits = [int(d) for d in card_number]
        checksum = 0

        # Double every second digit from right
        for i in range(len(digits) - 2, -1, -2):
            digits[i] *= 2
            if digits[i] > 9:
                digits[i] -= 9

        return sum(digits) % 10 == 0

    @staticmethod
    def validate_expiry(month: int, year: int) -> bool:
        """Validate card expiry date"""
        now = datetime.now()

        if year < now.year:
            return False
        if year == now.year and month < now.month:
            return False

        return 1 <= month <= 12

    @staticmethod
    def validate_cvv(cvv: str) -> bool:
        """Validate CVV code"""
        return cvv.isdigit() and len(cvv) in [3, 4]