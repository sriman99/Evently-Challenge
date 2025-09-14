"""
WebSocket endpoints for real-time updates
"""

from typing import List, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import json
import asyncio

from app.core.redis import get_redis
from app.core.security import decode_token

router = APIRouter()

# Store active connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        if client_id not in self.active_connections:
            self.active_connections[client_id] = []
        self.active_connections[client_id].append(websocket)

    def disconnect(self, websocket: WebSocket, client_id: str):
        if client_id in self.active_connections:
            self.active_connections[client_id].remove(websocket)
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]

    async def send_personal_message(self, message: str, client_id: str):
        if client_id in self.active_connections:
            for connection in self.active_connections[client_id]:
                await connection.send_text(message)

    async def broadcast_to_event(self, message: str, event_id: str):
        # Broadcast to all users watching this event
        event_key = f"event_{event_id}"
        if event_key in self.active_connections:
            for connection in self.active_connections[event_key]:
                await connection.send_text(message)


manager = ConnectionManager()


@router.websocket("/events/{event_id}")
async def websocket_event_updates(
    websocket: WebSocket,
    event_id: str,
    redis_client = Depends(get_redis)
):
    """
    WebSocket endpoint for real-time event updates (seat availability, etc.)
    """
    client_id = f"event_{event_id}"
    await manager.connect(websocket, client_id)

    try:
        # Subscribe to Redis channel for this event
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"event_updates:{event_id}")

        while True:
            # Check for messages from Redis
            message = await pubsub.get_message(ignore_subscribe_messages=True)
            if message and message["type"] == "message":
                # Send update to client
                await websocket.send_text(message["data"].decode())

            # Also handle incoming messages from client (like heartbeat)
            try:
                client_message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=0.1
                )
                if client_message == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket, client_id)
        await pubsub.unsubscribe(f"event_updates:{event_id}")


@router.websocket("/user/{user_id}")
async def websocket_user_notifications(
    websocket: WebSocket,
    user_id: str,
    token: str = None
):
    """
    WebSocket endpoint for user-specific notifications
    """
    # Verify token
    if not token:
        await websocket.close(code=1008, reason="Missing authentication")
        return

    try:
        payload = decode_token(token)
        if payload.get("sub") != user_id:
            await websocket.close(code=1008, reason="Invalid authentication")
            return
    except Exception:
        await websocket.close(code=1008, reason="Invalid token")
        return

    await manager.connect(websocket, user_id)

    try:
        while True:
            # Keep connection alive and handle messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)