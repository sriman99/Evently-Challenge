"""
WebSocket Service for Real-time Updates
Handles real-time seat availability and booking notifications
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set, Optional
import json
import asyncio
import logging
from datetime import datetime
from app.core.redis import redis_manager

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""

    def __init__(self):
        # Active connections by event_id
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # User connections for personal notifications
        self.user_connections: Dict[str, WebSocket] = {}
        # Connection metadata
        self.connection_metadata: Dict[WebSocket, Dict] = {}

    async def connect(
        self,
        websocket: WebSocket,
        event_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()

        # Store connection metadata
        self.connection_metadata[websocket] = {
            "event_id": event_id,
            "user_id": user_id,
            "connected_at": datetime.utcnow().isoformat()
        }

        # Register for event updates
        if event_id:
            if event_id not in self.active_connections:
                self.active_connections[event_id] = set()
            self.active_connections[event_id].add(websocket)
            logger.info(f"Client connected to event {event_id}")

        # Register for user notifications
        if user_id:
            self.user_connections[user_id] = websocket
            logger.info(f"User {user_id} connected")

        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "timestamp": datetime.utcnow().isoformat()
        })

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        metadata = self.connection_metadata.get(websocket, {})

        # Remove from event connections
        event_id = metadata.get("event_id")
        if event_id and event_id in self.active_connections:
            self.active_connections[event_id].discard(websocket)
            if not self.active_connections[event_id]:
                del self.active_connections[event_id]

        # Remove from user connections
        user_id = metadata.get("user_id")
        if user_id and user_id in self.user_connections:
            if self.user_connections[user_id] == websocket:
                del self.user_connections[user_id]

        # Clean up metadata
        if websocket in self.connection_metadata:
            del self.connection_metadata[websocket]

        logger.info(f"Client disconnected")

    async def send_personal_message(self, user_id: str, message: Dict):
        """Send a message to a specific user"""
        if user_id in self.user_connections:
            websocket = self.user_connections[user_id]
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")
                self.disconnect(websocket)

    async def broadcast_to_event(self, event_id: str, message: Dict):
        """Broadcast a message to all clients watching an event"""
        if event_id in self.active_connections:
            disconnected = []

            for websocket in self.active_connections[event_id]:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to event {event_id}: {e}")
                    disconnected.append(websocket)

            # Clean up disconnected clients
            for websocket in disconnected:
                self.disconnect(websocket)

    async def broadcast_seat_update(
        self,
        event_id: str,
        seat_ids: List[str],
        status: str,
        user_id: Optional[str] = None
    ):
        """Broadcast seat availability update"""
        message = {
            "type": "seat_update",
            "event_id": event_id,
            "seats": seat_ids,
            "status": status,  # "reserved", "available", "booked"
            "timestamp": datetime.utcnow().isoformat()
        }

        if user_id:
            message["user_id"] = user_id

        await self.broadcast_to_event(event_id, message)

        # Also publish to Redis for other server instances
        await redis_manager.publish(f"event:{event_id}:updates", json.dumps(message))

    async def broadcast_booking_update(
        self,
        event_id: str,
        available_seats: int,
        total_bookings: int
    ):
        """Broadcast booking statistics update"""
        message = {
            "type": "booking_stats",
            "event_id": event_id,
            "available_seats": available_seats,
            "total_bookings": total_bookings,
            "timestamp": datetime.utcnow().isoformat()
        }

        await self.broadcast_to_event(event_id, message)

    async def send_booking_confirmation(
        self,
        user_id: str,
        booking_details: Dict
    ):
        """Send booking confirmation to user"""
        message = {
            "type": "booking_confirmation",
            "booking_id": booking_details["booking_id"],
            "event_name": booking_details["event_name"],
            "seats": booking_details["seats"],
            "status": "confirmed",
            "timestamp": datetime.utcnow().isoformat()
        }

        await self.send_personal_message(user_id, message)

    async def send_payment_status(
        self,
        user_id: str,
        payment_status: str,
        booking_id: str
    ):
        """Send payment status update to user"""
        message = {
            "type": "payment_status",
            "booking_id": booking_id,
            "status": payment_status,
            "timestamp": datetime.utcnow().isoformat()
        }

        await self.send_personal_message(user_id, message)


class WebSocketHandler:
    """Handles WebSocket message processing"""

    def __init__(self, manager: ConnectionManager):
        self.manager = manager

    async def handle_client_message(
        self,
        websocket: WebSocket,
        message: Dict
    ):
        """Process messages received from clients"""
        message_type = message.get("type")

        if message_type == "ping":
            # Respond to ping
            await websocket.send_json({
                "type": "pong",
                "timestamp": datetime.utcnow().isoformat()
            })

        elif message_type == "subscribe_event":
            # Subscribe to event updates
            event_id = message.get("event_id")
            if event_id:
                metadata = self.manager.connection_metadata.get(websocket, {})
                metadata["event_id"] = event_id
                if event_id not in self.manager.active_connections:
                    self.manager.active_connections[event_id] = set()
                self.manager.active_connections[event_id].add(websocket)

                await websocket.send_json({
                    "type": "subscribed",
                    "event_id": event_id,
                    "timestamp": datetime.utcnow().isoformat()
                })

        elif message_type == "unsubscribe_event":
            # Unsubscribe from event updates
            event_id = message.get("event_id")
            if event_id and event_id in self.manager.active_connections:
                self.manager.active_connections[event_id].discard(websocket)

                await websocket.send_json({
                    "type": "unsubscribed",
                    "event_id": event_id,
                    "timestamp": datetime.utcnow().isoformat()
                })

        elif message_type == "get_seat_status":
            # Request current seat status
            event_id = message.get("event_id")
            seat_ids = message.get("seat_ids", [])

            # Fetch seat status from Redis or database
            seat_status = await self._get_seat_status(event_id, seat_ids)

            await websocket.send_json({
                "type": "seat_status",
                "event_id": event_id,
                "seats": seat_status,
                "timestamp": datetime.utcnow().isoformat()
            })

    async def _get_seat_status(
        self,
        event_id: str,
        seat_ids: List[str]
    ) -> Dict[str, str]:
        """Get current status of seats"""
        seat_status = {}

        for seat_id in seat_ids:
            # Check Redis for seat lock
            lock_key = f"seat_lock:{event_id}:{seat_id}"
            is_locked = await redis_manager.exists(lock_key)

            if is_locked:
                seat_status[seat_id] = "reserved"
            else:
                # Check database for permanent booking
                # This would be implemented with actual database query
                seat_status[seat_id] = "available"

        return seat_status


# Global connection manager
connection_manager = ConnectionManager()
websocket_handler = WebSocketHandler(connection_manager)


async def websocket_endpoint(websocket: WebSocket, event_id: Optional[str] = None, user_id: Optional[str] = None):
    """WebSocket endpoint for real-time updates"""
    await connection_manager.connect(websocket, event_id, user_id)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            await websocket_handler.handle_client_message(websocket, data)

    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        connection_manager.disconnect(websocket)