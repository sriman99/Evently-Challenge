"""
SMS Service with Twilio Integration
Handles SMS notifications for bookings and reminders
"""

from twilio.rest import Client
from typing import List, Dict, Optional
import logging
from app.core.config import settings
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)


class SMSService:
    """Service for handling SMS operations"""

    def __init__(self):
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.from_number = settings.TWILIO_PHONE_NUMBER

    async def send_sms(
        self,
        to_number: str,
        message: str
    ) -> Dict:
        """Send an SMS message"""
        try:
            # Validate phone number format
            if not self._validate_phone_number(to_number):
                raise ValueError(f"Invalid phone number: {to_number}")

            # Send SMS
            message = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number
            )

            logger.info(f"SMS sent to {to_number}: {message.sid}")

            return {
                "success": True,
                "message_id": message.sid,
                "status": message.status,
                "to": to_number
            }

        except Exception as e:
            logger.error(f"Error sending SMS: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "to": to_number
            }

    async def send_booking_confirmation_sms(
        self,
        phone_number: str,
        booking_details: Dict
    ) -> Dict:
        """Send booking confirmation SMS"""
        message = f"""
Evently Booking Confirmed!
Event: {booking_details['event_name']}
Date: {booking_details['event_date']}
Time: {booking_details['event_time']}
Venue: {booking_details['venue_name']}
Seats: {', '.join(booking_details['seats'])}
Booking ID: {booking_details['booking_id'][:8]}

Check your email for the QR code ticket.
        """.strip()

        return await self.send_sms(phone_number, message)

    async def send_event_reminder_sms(
        self,
        phone_number: str,
        event_details: Dict
    ) -> Dict:
        """Send event reminder SMS"""
        message = f"""
Reminder: Your event is tomorrow!
{event_details['event_name']}
{event_details['event_time']} at {event_details['venue_name']}
Don't forget your ticket!
        """.strip()

        return await self.send_sms(phone_number, message)

    async def send_otp(
        self,
        phone_number: str,
        otp_code: str
    ) -> Dict:
        """Send OTP for two-factor authentication"""
        message = f"Your Evently verification code is: {otp_code}. Valid for 5 minutes."

        return await self.send_sms(phone_number, message)

    async def send_booking_cancellation_sms(
        self,
        phone_number: str,
        booking_id: str,
        refund_amount: float
    ) -> Dict:
        """Send booking cancellation SMS"""
        message = f"""
Your Evently booking {booking_id[:8]} has been cancelled.
Refund of ${refund_amount:.2f} will be processed within 5-7 days.
        """.strip()

        return await self.send_sms(phone_number, message)

    async def send_bulk_sms(
        self,
        recipients: List[Dict],
        message_template: str
    ) -> Dict:
        """Send bulk SMS to multiple recipients"""
        results = {
            "sent": [],
            "failed": []
        }

        # Send SMS in batches to avoid rate limiting
        for recipient in recipients:
            # Customize message for each recipient
            message = message_template.format(**recipient)

            result = await self.send_sms(
                to_number=recipient["phone_number"],
                message=message
            )

            if result["success"]:
                results["sent"].append(recipient["phone_number"])
            else:
                results["failed"].append({
                    "number": recipient["phone_number"],
                    "error": result.get("error")
                })

            # Rate limiting delay
            await asyncio.sleep(0.5)

        return results

    def _validate_phone_number(self, phone_number: str) -> bool:
        """Validate phone number format"""
        # Basic validation - should start with + and contain only digits
        if not phone_number.startswith("+"):
            return False

        # Remove + and check if rest are digits
        number_part = phone_number[1:]
        return number_part.isdigit() and 10 <= len(number_part) <= 15

    async def verify_phone_number(self, phone_number: str) -> bool:
        """Verify if phone number is valid using Twilio Lookup API"""
        try:
            phone = self.client.lookups.v1.phone_numbers(phone_number).fetch()
            return phone.phone_number is not None
        except:
            return False


# Initialize global SMS service
sms_service = SMSService()