"""
Endpoint WebSocket cho các trạm kiosk.
Kiosk kết nối vào đây để nhận sự kiện chấm công theo thời gian thực.
"""
import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# device_id → kết nối WebSocket
_connections: Dict[str, WebSocket] = {}


class KioskConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, device_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[device_id] = websocket
        logger.info(f"Kiosk '{device_id}' đã kết nối. Tổng: {len(self.active_connections)}")

    def disconnect(self, device_id: str):
        self.active_connections.pop(device_id, None)
        logger.info(f"Kiosk '{device_id}' đã ngắt kết nối. Tổng: {len(self.active_connections)}")

    async def send_to(self, device_id: str, message: dict):
        ws = self.active_connections.get(device_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.error(f"Lỗi khi gửi tới kiosk '{device_id}': {e}")
                self.disconnect(device_id)

    async def broadcast(self, message: dict):
        dead = []
        for device_id, ws in list(self.active_connections.items()):
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.error(f"Broadcast thất bại cho kiosk '{device_id}': {e}")
                dead.append(device_id)
        for d in dead:
            self.disconnect(d)


manager = KioskConnectionManager()


async def broadcast_attendance_event(event_data: dict):
    """Được các endpoint chấm công gọi để đẩy sự kiện tới tất cả kiosk đang kết nối."""
    await manager.broadcast(event_data)


@router.websocket("/kiosk/{device_id}")
async def kiosk_websocket(websocket: WebSocket, device_id: str):
    await manager.connect(device_id, websocket)
    try:
        # Gửi tin nhắn chào mừng
        await websocket.send_json({
            "event": "connected",
            "device_id": device_id,
            "message": "Đã kết nối vào hệ thống chấm công",
        })

        while True:
            # Giữ kết nối + xử lý tin nhắn từ kiosk gửi lên
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                event = msg.get("event")
                if event == "ping":
                    await websocket.send_json({"event": "pong"})
                else:
                    logger.debug(f"Kiosk '{device_id}' gửi: {msg}")
            except json.JSONDecodeError:
                await websocket.send_json({"event": "error", "message": "JSON không hợp lệ"})

    except WebSocketDisconnect:
        manager.disconnect(device_id)
    except Exception as e:
        logger.error(f"Lỗi WebSocket cho kiosk '{device_id}': {e}")
        manager.disconnect(device_id)
