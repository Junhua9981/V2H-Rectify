"""WebSocket endpoint for real-time OCR progress updates."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.schemas import WSBatchProgressMessage, WSProgressMessage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Active connections per task_id
_connections: Dict[str, Set[WebSocket]] = {}


async def broadcast_progress(
    task_id: str,
    stage: str,
    progress: float,
    message: str = "",
    status: str = "processing",
) -> None:
    """Send a progress update to all WebSocket clients watching *task_id*."""
    sockets = _connections.get(task_id, set())
    if not sockets:
        return

    payload = WSProgressMessage(
        task_id=task_id,
        stage=stage,
        progress=progress,
        message=message,
        status=status,
    ).model_dump_json()

    dead: list[WebSocket] = []
    for ws in sockets:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)

    for ws in dead:
        sockets.discard(ws)


async def broadcast_batch_progress(
    batch_id: str,
    progress: float,
    completed: int,
    failed: int,
    total: int,
    status: str = "processing",
) -> None:
    """Send a batch progress update to all WebSocket clients watching *batch_id*."""
    sockets = _connections.get(f"batch:{batch_id}", set())
    if not sockets:
        return

    payload = WSBatchProgressMessage(
        batch_id=batch_id,
        progress=progress,
        completed=completed,
        failed=failed,
        total=total,
        status=status,
    ).model_dump_json()

    dead: list[WebSocket] = []
    for ws in sockets:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)

    for ws in dead:
        sockets.discard(ws)


@router.websocket("/ws/batch/{batch_id}")
async def ws_batch_progress(websocket: WebSocket, batch_id: str) -> None:
    """Client connects to receive batch-level progress updates."""
    await websocket.accept()
    key = f"batch:{batch_id}"

    if key not in _connections:
        _connections[key] = set()
    _connections[key].add(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.get(key, set()).discard(websocket)
        if key in _connections and not _connections[key]:
            del _connections[key]


@router.websocket("/ws/{task_id}")
async def ws_progress(websocket: WebSocket, task_id: str) -> None:
    """Client connects to receive progress updates for a given task."""
    await websocket.accept()

    if task_id not in _connections:
        _connections[task_id] = set()
    _connections[task_id].add(websocket)

    try:
        # Keep connection alive — wait for client disconnect
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.get(task_id, set()).discard(websocket)
        if task_id in _connections and not _connections[task_id]:
            del _connections[task_id]
