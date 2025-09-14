"""
Analytics Service for Dashboard and Reporting
Provides comprehensive analytics for events, bookings, and revenue
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta, date
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, extract
from app.models.event import Event
from app.models.booking import Booking
from app.models.payment import Payment
from app.models.user import User
from app.models.venue import Venue
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for generating analytics and reports"""

    @staticmethod
    async def get_dashboard_metrics(
        db: AsyncSession,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict:
        """Get overall dashboard metrics"""
        try:
            # Default to last 30 days if no dates provided
            if not end_date:
                end_date = date.today()
            if not start_date:
                start_date = end_date - timedelta(days=30)

            metrics = {}

            # Total revenue
            revenue_query = select(func.sum(Payment.amount)).where(
                and_(
                    Payment.status == "completed",
                    Payment.created_at >= start_date,
                    Payment.created_at <= end_date
                )
            )
            result = await db.execute(revenue_query)
            metrics["total_revenue"] = float(result.scalar() or 0)

            # Total bookings
            bookings_query = select(func.count(Booking.id)).where(
                and_(
                    Booking.created_at >= start_date,
                    Booking.created_at <= end_date
                )
            )
            result = await db.execute(bookings_query)
            metrics["total_bookings"] = result.scalar() or 0

            # Active events
            events_query = select(func.count(Event.id)).where(
                and_(
                    Event.start_time >= datetime.now(),
                    Event.status == "active"
                )
            )
            result = await db.execute(events_query)
            metrics["active_events"] = result.scalar() or 0

            # Total users
            users_query = select(func.count(User.id))
            result = await db.execute(users_query)
            metrics["total_users"] = result.scalar() or 0

            # New users (in period)
            new_users_query = select(func.count(User.id)).where(
                and_(
                    User.created_at >= start_date,
                    User.created_at <= end_date
                )
            )
            result = await db.execute(new_users_query)
            metrics["new_users"] = result.scalar() or 0

            # Average booking value
            avg_booking_query = select(func.avg(Payment.amount)).where(
                and_(
                    Payment.status == "completed",
                    Payment.created_at >= start_date,
                    Payment.created_at <= end_date
                )
            )
            result = await db.execute(avg_booking_query)
            metrics["average_booking_value"] = float(result.scalar() or 0)

            # Conversion rate (simplified)
            metrics["conversion_rate"] = 0.0
            if metrics["total_users"] > 0:
                converted_users_query = select(func.count(func.distinct(Booking.user_id))).where(
                    and_(
                        Booking.created_at >= start_date,
                        Booking.created_at <= end_date
                    )
                )
                result = await db.execute(converted_users_query)
                converted_users = result.scalar() or 0
                metrics["conversion_rate"] = (converted_users / metrics["total_users"]) * 100

            return metrics

        except Exception as e:
            logger.error(f"Error getting dashboard metrics: {str(e)}")
            raise

    @staticmethod
    async def get_revenue_analytics(
        db: AsyncSession,
        start_date: date,
        end_date: date,
        group_by: str = "day"
    ) -> List[Dict]:
        """Get revenue analytics over time"""
        try:
            # Determine grouping
            if group_by == "day":
                date_trunc = func.date_trunc('day', Payment.created_at)
            elif group_by == "week":
                date_trunc = func.date_trunc('week', Payment.created_at)
            elif group_by == "month":
                date_trunc = func.date_trunc('month', Payment.created_at)
            else:
                date_trunc = func.date_trunc('day', Payment.created_at)

            # Query revenue by period
            query = select(
                date_trunc.label("period"),
                func.sum(Payment.amount).label("revenue"),
                func.count(Payment.id).label("transactions")
            ).where(
                and_(
                    Payment.status == "completed",
                    Payment.created_at >= start_date,
                    Payment.created_at <= end_date
                )
            ).group_by(date_trunc).order_by(date_trunc)

            result = await db.execute(query)
            data = []

            for row in result:
                data.append({
                    "period": row.period.isoformat() if row.period else None,
                    "revenue": float(row.revenue or 0),
                    "transactions": row.transactions
                })

            return data

        except Exception as e:
            logger.error(f"Error getting revenue analytics: {str(e)}")
            raise

    @staticmethod
    async def get_event_analytics(
        db: AsyncSession,
        event_id: str
    ) -> Dict:
        """Get detailed analytics for a specific event"""
        try:
            # Get event details
            event = await db.get(Event, event_id)
            if not event:
                raise ValueError("Event not found")

            analytics = {
                "event_id": event_id,
                "event_name": event.name,
                "event_date": event.start_time.isoformat()
            }

            # Total bookings
            bookings_query = select(func.count(Booking.id)).where(
                Booking.event_id == event_id
            )
            result = await db.execute(bookings_query)
            analytics["total_bookings"] = result.scalar() or 0

            # Total revenue
            revenue_query = select(func.sum(Payment.amount)).join(
                Booking, Payment.booking_id == Booking.id
            ).where(
                and_(
                    Booking.event_id == event_id,
                    Payment.status == "completed"
                )
            )
            result = await db.execute(revenue_query)
            analytics["total_revenue"] = float(result.scalar() or 0)

            # Sold seats
            sold_seats_query = select(func.count(Booking.id)).where(
                and_(
                    Booking.event_id == event_id,
                    Booking.status.in_(["confirmed", "completed"])
                )
            )
            result = await db.execute(sold_seats_query)
            analytics["sold_seats"] = result.scalar() or 0

            # Available seats
            analytics["available_seats"] = event.available_seats
            analytics["total_capacity"] = event.capacity

            # Occupancy rate
            if event.capacity > 0:
                analytics["occupancy_rate"] = (
                    (event.capacity - event.available_seats) / event.capacity
                ) * 100
            else:
                analytics["occupancy_rate"] = 0

            # Sales by day
            sales_by_day_query = select(
                func.date_trunc('day', Booking.created_at).label("day"),
                func.count(Booking.id).label("bookings")
            ).where(
                Booking.event_id == event_id
            ).group_by(
                func.date_trunc('day', Booking.created_at)
            ).order_by(
                func.date_trunc('day', Booking.created_at)
            )

            result = await db.execute(sales_by_day_query)
            analytics["sales_timeline"] = [
                {
                    "date": row.day.isoformat() if row.day else None,
                    "bookings": row.bookings
                }
                for row in result
            ]

            return analytics

        except Exception as e:
            logger.error(f"Error getting event analytics: {str(e)}")
            raise

    @staticmethod
    async def get_venue_analytics(
        db: AsyncSession,
        venue_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict:
        """Get analytics for a specific venue"""
        try:
            venue = await db.get(Venue, venue_id)
            if not venue:
                raise ValueError("Venue not found")

            analytics = {
                "venue_id": venue_id,
                "venue_name": venue.name
            }

            # Date range
            if not end_date:
                end_date = date.today()
            if not start_date:
                start_date = end_date - timedelta(days=30)

            # Total events
            events_query = select(func.count(Event.id)).where(
                and_(
                    Event.venue_id == venue_id,
                    Event.start_time >= start_date,
                    Event.end_time <= end_date
                )
            )
            result = await db.execute(events_query)
            analytics["total_events"] = result.scalar() or 0

            # Total revenue
            revenue_query = select(func.sum(Payment.amount)).join(
                Booking, Payment.booking_id == Booking.id
            ).join(
                Event, Booking.event_id == Event.id
            ).where(
                and_(
                    Event.venue_id == venue_id,
                    Payment.status == "completed",
                    Payment.created_at >= start_date,
                    Payment.created_at <= end_date
                )
            )
            result = await db.execute(revenue_query)
            analytics["total_revenue"] = float(result.scalar() or 0)

            # Average occupancy
            occupancy_query = select(
                func.avg(
                    (Event.capacity - Event.available_seats) * 100.0 / Event.capacity
                )
            ).where(
                and_(
                    Event.venue_id == venue_id,
                    Event.capacity > 0,
                    Event.start_time >= start_date,
                    Event.end_time <= end_date
                )
            )
            result = await db.execute(occupancy_query)
            analytics["average_occupancy"] = float(result.scalar() or 0)

            # Popular event categories
            category_query = select(
                Event.category,
                func.count(Event.id).label("count")
            ).where(
                and_(
                    Event.venue_id == venue_id,
                    Event.start_time >= start_date,
                    Event.end_time <= end_date
                )
            ).group_by(Event.category).order_by(func.count(Event.id).desc())

            result = await db.execute(category_query)
            analytics["popular_categories"] = [
                {"category": row.category, "count": row.count}
                for row in result
            ]

            return analytics

        except Exception as e:
            logger.error(f"Error getting venue analytics: {str(e)}")
            raise

    @staticmethod
    async def get_user_behavior_analytics(
        db: AsyncSession,
        start_date: date,
        end_date: date
    ) -> Dict:
        """Get user behavior analytics"""
        try:
            analytics = {}

            # Most active users
            active_users_query = select(
                User.id,
                User.email,
                User.full_name,
                func.count(Booking.id).label("bookings_count")
            ).join(
                Booking, User.id == Booking.user_id
            ).where(
                and_(
                    Booking.created_at >= start_date,
                    Booking.created_at <= end_date
                )
            ).group_by(
                User.id, User.email, User.full_name
            ).order_by(
                func.count(Booking.id).desc()
            ).limit(10)

            result = await db.execute(active_users_query)
            analytics["top_users"] = [
                {
                    "user_id": str(row.id),
                    "email": row.email,
                    "name": row.full_name,
                    "bookings": row.bookings_count
                }
                for row in result
            ]

            # User retention (simplified)
            retention_query = select(
                func.date_trunc('month', User.created_at).label("cohort"),
                func.count(func.distinct(User.id)).label("users")
            ).where(
                User.created_at >= start_date
            ).group_by(
                func.date_trunc('month', User.created_at)
            )

            result = await db.execute(retention_query)
            analytics["user_cohorts"] = [
                {
                    "cohort": row.cohort.isoformat() if row.cohort else None,
                    "users": row.users
                }
                for row in result
            ]

            # Popular event times
            booking_times_query = select(
                extract('hour', Event.start_time).label("hour"),
                func.count(Booking.id).label("bookings")
            ).join(
                Event, Booking.event_id == Event.id
            ).where(
                and_(
                    Booking.created_at >= start_date,
                    Booking.created_at <= end_date
                )
            ).group_by(
                extract('hour', Event.start_time)
            ).order_by(
                extract('hour', Event.start_time)
            )

            result = await db.execute(booking_times_query)
            analytics["popular_times"] = [
                {"hour": int(row.hour), "bookings": row.bookings}
                for row in result
            ]

            return analytics

        except Exception as e:
            logger.error(f"Error getting user behavior analytics: {str(e)}")
            raise

    @staticmethod
    async def export_analytics_report(
        db: AsyncSession,
        report_type: str,
        start_date: date,
        end_date: date,
        format: str = "csv"
    ) -> bytes:
        """Export analytics report in various formats"""
        try:
            # Get data based on report type
            if report_type == "revenue":
                data = await AnalyticsService.get_revenue_analytics(
                    db, start_date, end_date, "day"
                )
                df = pd.DataFrame(data)

            elif report_type == "bookings":
                # Get bookings data
                query = select(
                    Booking.id,
                    Booking.created_at,
                    User.email,
                    Event.name,
                    Booking.total_amount,
                    Booking.status
                ).join(
                    User, Booking.user_id == User.id
                ).join(
                    Event, Booking.event_id == Event.id
                ).where(
                    and_(
                        Booking.created_at >= start_date,
                        Booking.created_at <= end_date
                    )
                )
                result = await db.execute(query)
                data = [
                    {
                        "booking_id": str(row.id),
                        "date": row.created_at.isoformat(),
                        "user": row.email,
                        "event": row.name,
                        "amount": float(row.total_amount),
                        "status": row.status
                    }
                    for row in result
                ]
                df = pd.DataFrame(data)

            else:
                raise ValueError(f"Invalid report type: {report_type}")

            # Export to requested format
            if format == "csv":
                output = BytesIO()
                df.to_csv(output, index=False)
                output.seek(0)
                return output.getvalue()

            elif format == "excel":
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, sheet_name='Report', index=False)
                output.seek(0)
                return output.getvalue()

            elif format == "json":
                return df.to_json(orient='records').encode()

            else:
                raise ValueError(f"Invalid format: {format}")

        except Exception as e:
            logger.error(f"Error exporting analytics report: {str(e)}")
            raise


# Initialize global analytics service
analytics_service = AnalyticsService()