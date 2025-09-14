"""
Ticket Generation Service
Handles QR code and PDF ticket generation for bookings
"""

import qrcode
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.graphics.shapes import Drawing, Line
from reportlab.graphics.barcode import code128
from typing import Dict, List, Optional
import base64
from datetime import datetime
import json
import logging
from PIL import Image as PILImage
import uuid

logger = logging.getLogger(__name__)


class TicketGenerator:
    """Service for generating event tickets"""

    @staticmethod
    def generate_qr_code(
        data: Dict,
        size: int = 300,
        border: int = 4
    ) -> bytes:
        """Generate QR code for ticket validation"""
        try:
            # Create QR code instance
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=border,
            )

            # Add data
            qr.add_data(json.dumps(data))
            qr.make(fit=True)

            # Create image
            img = qr.make_image(fill_color="black", back_color="white")

            # Resize if needed
            if size != img.size[0]:
                img = img.resize((size, size), PILImage.LANCZOS)

            # Convert to bytes
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)

            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Error generating QR code: {str(e)}")
            raise

    @staticmethod
    def generate_pdf_ticket(
        booking_details: Dict,
        qr_code_data: bytes
    ) -> bytes:
        """Generate PDF ticket with all booking details"""
        try:
            # Create buffer
            buffer = BytesIO()

            # Create PDF document
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18,
            )

            # Container for the 'Flowable' objects
            elements = []

            # Define styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#2c3e50'),
                spaceAfter=30,
                alignment=1  # Center
            )

            event_style = ParagraphStyle(
                'EventName',
                parent=styles['Heading2'],
                fontSize=20,
                textColor=colors.HexColor('#34495e'),
                spaceAfter=20,
                alignment=1
            )

            # Add title
            elements.append(Paragraph("EVENT TICKET", title_style))
            elements.append(Spacer(1, 0.2 * inch))

            # Add event name
            elements.append(Paragraph(booking_details['event_name'], event_style))
            elements.append(Spacer(1, 0.3 * inch))

            # Create ticket info table
            ticket_data = [
                ['Booking ID:', booking_details['booking_id'][:8].upper()],
                ['Date:', booking_details['event_date']],
                ['Time:', booking_details['event_time']],
                ['Venue:', booking_details['venue_name']],
                ['Address:', booking_details.get('venue_address', 'N/A')],
                ['Seats:', ', '.join(booking_details['seats'])],
                ['Ticket Type:', booking_details.get('ticket_type', 'General')],
                ['Name:', booking_details['user_name']],
                ['Email:', booking_details['user_email']],
            ]

            # Create and style the table
            ticket_table = Table(ticket_data, colWidths=[2 * inch, 4 * inch])
            ticket_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 12),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
            ]))

            elements.append(ticket_table)
            elements.append(Spacer(1, 0.5 * inch))

            # Add QR code
            if qr_code_data:
                qr_img = Image(BytesIO(qr_code_data), width=2.5 * inch, height=2.5 * inch)
                # Center the QR code
                qr_table = Table([[qr_img]], colWidths=[6 * inch])
                qr_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                elements.append(qr_table)
                elements.append(Spacer(1, 0.2 * inch))

            # Add validation text
            validation_style = ParagraphStyle(
                'Validation',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.grey,
                alignment=1
            )
            elements.append(Paragraph("Present this QR code at the venue for entry", validation_style))
            elements.append(Spacer(1, 0.3 * inch))

            # Add barcode (alternative to QR)
            barcode_value = booking_details['booking_id'].replace('-', '')[:12]
            barcode = code128.Code128(barcode_value, barHeight=0.5 * inch, barWidth=1.5)
            elements.append(barcode)
            elements.append(Spacer(1, 0.1 * inch))
            elements.append(Paragraph(barcode_value, validation_style))

            # Add footer
            elements.append(Spacer(1, 0.5 * inch))
            footer_style = ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=8,
                textColor=colors.grey,
                alignment=1
            )

            footer_text = f"""
            <para align=center>
            Terms & Conditions: This ticket is non-transferable.
            Please arrive 30 minutes before the event starts.
            No refunds unless event is cancelled.<br/>
            Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}
            </para>
            """
            elements.append(Paragraph(footer_text, footer_style))

            # Add page break if multiple tickets
            if len(booking_details.get('seats', [])) > 1:
                for i, seat in enumerate(booking_details['seats'][1:], 1):
                    elements.append(PageBreak())
                    # Add duplicate ticket for each seat
                    elements.append(Paragraph("EVENT TICKET", title_style))
                    elements.append(Paragraph(f"Seat: {seat}", event_style))
                    # ... (repeat ticket content for each seat)

            # Build PDF
            doc.build(elements)

            # Get PDF data
            buffer.seek(0)
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Error generating PDF ticket: {str(e)}")
            raise

    @staticmethod
    def generate_ticket_package(booking_details: Dict) -> Dict[str, bytes]:
        """Generate complete ticket package with QR and PDF"""
        try:
            # Prepare QR code data
            qr_data = {
                "booking_id": booking_details['booking_id'],
                "event_id": booking_details['event_id'],
                "user_id": booking_details['user_id'],
                "seats": booking_details['seats'],
                "validation_code": str(uuid.uuid4())[:8],
                "timestamp": datetime.utcnow().isoformat()
            }

            # Generate QR code
            qr_code = TicketGenerator.generate_qr_code(qr_data)

            # Generate PDF ticket
            pdf_ticket = TicketGenerator.generate_pdf_ticket(
                booking_details,
                qr_code
            )

            return {
                "qr_code": qr_code,
                "pdf_ticket": pdf_ticket,
                "validation_code": qr_data["validation_code"]
            }

        except Exception as e:
            logger.error(f"Error generating ticket package: {str(e)}")
            raise

    @staticmethod
    def validate_ticket_qr(qr_data: str) -> Dict:
        """Validate QR code data from scanned ticket"""
        try:
            # Parse QR data
            data = json.loads(qr_data)

            # Validate required fields
            required_fields = ['booking_id', 'event_id', 'validation_code']
            for field in required_fields:
                if field not in data:
                    return {
                        "valid": False,
                        "error": f"Missing field: {field}"
                    }

            # Additional validation would check against database
            # This is a simplified version
            return {
                "valid": True,
                "booking_id": data['booking_id'],
                "event_id": data['event_id'],
                "seats": data.get('seats', []),
                "validation_code": data['validation_code']
            }

        except json.JSONDecodeError:
            return {
                "valid": False,
                "error": "Invalid QR code format"
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }

    @staticmethod
    def generate_event_badge(
        attendee_details: Dict,
        event_details: Dict,
        photo_data: Optional[bytes] = None
    ) -> bytes:
        """Generate event badge/pass for attendees"""
        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=(3.5 * inch, 2.25 * inch),  # Standard badge size
                rightMargin=10,
                leftMargin=10,
                topMargin=10,
                bottomMargin=10,
            )

            elements = []
            styles = getSampleStyleSheet()

            # Add event name
            event_style = ParagraphStyle(
                'EventBadge',
                parent=styles['Normal'],
                fontSize=14,
                textColor=colors.HexColor('#2c3e50'),
                alignment=1
            )
            elements.append(Paragraph(event_details['event_name'], event_style))

            # Add attendee name
            name_style = ParagraphStyle(
                'AttendeeName',
                parent=styles['Heading2'],
                fontSize=18,
                textColor=colors.black,
                alignment=1
            )
            elements.append(Paragraph(attendee_details['name'], name_style))

            # Add role/ticket type
            role_style = ParagraphStyle(
                'Role',
                parent=styles['Normal'],
                fontSize=12,
                textColor=colors.HexColor('#7f8c8d'),
                alignment=1
            )
            elements.append(Paragraph(attendee_details.get('ticket_type', 'ATTENDEE'), role_style))

            # Add QR code for quick scan
            qr_data = {
                "attendee_id": attendee_details['id'],
                "event_id": event_details['id'],
                "type": "badge"
            }
            qr_code = TicketGenerator.generate_qr_code(qr_data, size=100)
            qr_img = Image(BytesIO(qr_code), width=0.8 * inch, height=0.8 * inch)
            elements.append(qr_img)

            doc.build(elements)
            buffer.seek(0)
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Error generating event badge: {str(e)}")
            raise


# Initialize global ticket generator
ticket_generator = TicketGenerator()