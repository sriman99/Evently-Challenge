"""
Email Service with SendGrid Integration
Handles all email notifications for the platform
"""

import os
from typing import List, Dict, Optional
from datetime import datetime
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment, FileContent, FileName, FileType
import base64
from jinja2 import Template
from app.core.config import settings
import asyncio

logger = logging.getLogger(__name__)


class EmailService:
    """Service for handling email operations"""

    def __init__(self):
        self.client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        self.from_email = settings.FROM_EMAIL
        self.templates = self._load_templates()

    def _load_templates(self) -> Dict[str, Template]:
        """Load email templates"""
        templates = {
            "booking_confirmation": Template("""
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body { font-family: Arial, sans-serif; line-height: 1.6; }
                        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                        .header { background: #4CAF50; color: white; padding: 20px; text-align: center; }
                        .content { padding: 20px; background: #f4f4f4; }
                        .ticket { border: 2px dashed #4CAF50; padding: 15px; margin: 20px 0; background: white; }
                        .footer { text-align: center; padding: 20px; color: #666; }
                        .button { display: inline-block; padding: 10px 20px; background: #4CAF50; color: white; text-decoration: none; border-radius: 5px; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Booking Confirmation</h1>
                        </div>
                        <div class="content">
                            <h2>Hi {{ user_name }},</h2>
                            <p>Your booking has been confirmed!</p>

                            <div class="ticket">
                                <h3>Event Details</h3>
                                <p><strong>Event:</strong> {{ event_name }}</p>
                                <p><strong>Date:</strong> {{ event_date }}</p>
                                <p><strong>Time:</strong> {{ event_time }}</p>
                                <p><strong>Venue:</strong> {{ venue_name }}</p>
                                <p><strong>Seats:</strong> {{ seats }}</p>
                                <p><strong>Booking ID:</strong> {{ booking_id }}</p>
                                <p><strong>Total Amount:</strong> ${{ total_amount }}</p>
                            </div>

                            <p>Your QR code is attached to this email. Please present it at the venue.</p>

                            <center>
                                <a href="{{ ticket_url }}" class="button">View Ticket</a>
                            </center>
                        </div>
                        <div class="footer">
                            <p>Thank you for choosing Evently!</p>
                            <p>If you have any questions, contact support@evently.com</p>
                        </div>
                    </div>
                </body>
                </html>
            """),

            "registration_welcome": Template("""
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body { font-family: Arial, sans-serif; }
                        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }
                        .content { padding: 30px; background: #f8f9fa; }
                        .button { display: inline-block; padding: 12px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1>Welcome to Evently!</h1>
                        </div>
                        <div class="content">
                            <h2>Hi {{ user_name }},</h2>
                            <p>Welcome to Evently - your gateway to amazing events!</p>
                            <p>Your account has been successfully created. You can now:</p>
                            <ul>
                                <li>Browse and book events</li>
                                <li>Save your favorite venues</li>
                                <li>Get personalized recommendations</li>
                                <li>Manage your bookings</li>
                            </ul>

                            <p>To verify your email address, please click the button below:</p>

                            <center>
                                <a href="{{ verification_url }}" class="button">Verify Email</a>
                            </center>

                            <p>If you didn't create this account, please ignore this email.</p>
                        </div>
                    </div>
                </body>
                </html>
            """),

            "password_reset": Template("""
                <!DOCTYPE html>
                <html>
                <body>
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2>Password Reset Request</h2>
                        <p>Hi {{ user_name }},</p>
                        <p>We received a request to reset your password. Click the link below to create a new password:</p>

                        <p><a href="{{ reset_url }}" style="display: inline-block; padding: 10px 20px; background: #4CAF50; color: white; text-decoration: none; border-radius: 5px;">Reset Password</a></p>

                        <p>This link will expire in 1 hour.</p>
                        <p>If you didn't request this, please ignore this email.</p>

                        <p>Best regards,<br>The Evently Team</p>
                    </div>
                </body>
                </html>
            """),

            "event_reminder": Template("""
                <!DOCTYPE html>
                <html>
                <body>
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2>Event Reminder</h2>
                        <p>Hi {{ user_name }},</p>
                        <p>This is a reminder that you have an upcoming event:</p>

                        <div style="border: 1px solid #ddd; padding: 15px; margin: 20px 0;">
                            <h3>{{ event_name }}</h3>
                            <p><strong>Date:</strong> {{ event_date }}</p>
                            <p><strong>Time:</strong> {{ event_time }}</p>
                            <p><strong>Venue:</strong> {{ venue_name }}</p>
                            <p><strong>Address:</strong> {{ venue_address }}</p>
                        </div>

                        <p>Don't forget to bring your ticket (QR code)!</p>

                        <p>See you there!</p>
                    </div>
                </body>
                </html>
            """),

            "booking_cancellation": Template("""
                <!DOCTYPE html>
                <html>
                <body>
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2>Booking Cancellation Confirmation</h2>
                        <p>Hi {{ user_name }},</p>
                        <p>Your booking has been cancelled as requested.</p>

                        <div style="border: 1px solid #ddd; padding: 15px; margin: 20px 0;">
                            <p><strong>Booking ID:</strong> {{ booking_id }}</p>
                            <p><strong>Event:</strong> {{ event_name }}</p>
                            <p><strong>Refund Amount:</strong> ${{ refund_amount }}</p>
                            <p><strong>Refund Status:</strong> {{ refund_status }}</p>
                        </div>

                        <p>The refund will be processed within 5-7 business days.</p>

                        <p>If you have any questions, please contact our support team.</p>
                    </div>
                </body>
                </html>
            """)
        }
        return templates

    async def send_email(
        self,
        to_email: str,
        subject: str,
        template_name: str,
        context: Dict,
        attachments: Optional[List[Dict]] = None
    ) -> bool:
        """Send an email using SendGrid"""
        try:
            # Render template
            template = self.templates.get(template_name)
            if not template:
                logger.error(f"Template {template_name} not found")
                return False

            html_content = template.render(**context)

            # Create message
            message = Mail(
                from_email=self.from_email,
                to_emails=to_email,
                subject=subject,
                html_content=html_content
            )

            # Add attachments if any
            if attachments:
                for attachment_data in attachments:
                    attachment = Attachment(
                        FileContent(attachment_data['content']),
                        FileName(attachment_data['filename']),
                        FileType(attachment_data['type'])
                    )
                    message.add_attachment(attachment)

            # Send email
            response = self.client.send(message)

            logger.info(f"Email sent to {to_email}: {response.status_code}")
            return response.status_code in [200, 201, 202]

        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return False

    async def send_booking_confirmation(
        self,
        user_email: str,
        user_name: str,
        booking_details: Dict,
        qr_code_data: Optional[bytes] = None
    ) -> bool:
        """Send booking confirmation email with QR code"""
        context = {
            "user_name": user_name,
            "event_name": booking_details["event_name"],
            "event_date": booking_details["event_date"],
            "event_time": booking_details["event_time"],
            "venue_name": booking_details["venue_name"],
            "seats": ", ".join(booking_details["seats"]),
            "booking_id": booking_details["booking_id"],
            "total_amount": booking_details["total_amount"],
            "ticket_url": f"{settings.FRONTEND_URL}/tickets/{booking_details['booking_id']}"
        }

        attachments = []
        if qr_code_data:
            attachments.append({
                "content": base64.b64encode(qr_code_data).decode(),
                "filename": f"ticket_{booking_details['booking_id']}.png",
                "type": "image/png"
            })

        return await self.send_email(
            to_email=user_email,
            subject=f"Booking Confirmation - {booking_details['event_name']}",
            template_name="booking_confirmation",
            context=context,
            attachments=attachments
        )

    async def send_registration_welcome(
        self,
        user_email: str,
        user_name: str,
        verification_token: str
    ) -> bool:
        """Send welcome email after registration"""
        context = {
            "user_name": user_name,
            "verification_url": f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
        }

        return await self.send_email(
            to_email=user_email,
            subject="Welcome to Evently!",
            template_name="registration_welcome",
            context=context
        )

    async def send_password_reset(
        self,
        user_email: str,
        user_name: str,
        reset_token: str
    ) -> bool:
        """Send password reset email"""
        context = {
            "user_name": user_name,
            "reset_url": f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        }

        return await self.send_email(
            to_email=user_email,
            subject="Password Reset Request",
            template_name="password_reset",
            context=context
        )

    async def send_event_reminder(
        self,
        user_email: str,
        user_name: str,
        event_details: Dict
    ) -> bool:
        """Send event reminder email"""
        context = {
            "user_name": user_name,
            "event_name": event_details["event_name"],
            "event_date": event_details["event_date"],
            "event_time": event_details["event_time"],
            "venue_name": event_details["venue_name"],
            "venue_address": event_details["venue_address"]
        }

        return await self.send_email(
            to_email=user_email,
            subject=f"Reminder: {event_details['event_name']} is tomorrow!",
            template_name="event_reminder",
            context=context
        )

    async def send_bulk_emails(
        self,
        recipients: List[Dict],
        subject: str,
        template_name: str,
        common_context: Dict
    ) -> Dict:
        """Send bulk emails to multiple recipients"""
        results = {
            "sent": [],
            "failed": []
        }

        # Send emails in batches to avoid rate limiting
        batch_size = 100
        for i in range(0, len(recipients), batch_size):
            batch = recipients[i:i + batch_size]

            tasks = []
            for recipient in batch:
                context = {**common_context, **recipient}
                task = self.send_email(
                    to_email=recipient["email"],
                    subject=subject,
                    template_name=template_name,
                    context=context
                )
                tasks.append(task)

            # Execute batch
            batch_results = await asyncio.gather(*tasks)

            for j, result in enumerate(batch_results):
                if result:
                    results["sent"].append(batch[j]["email"])
                else:
                    results["failed"].append(batch[j]["email"])

            # Rate limiting delay
            await asyncio.sleep(1)

        return results


# Initialize global email service
email_service = EmailService()