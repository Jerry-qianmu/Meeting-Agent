# -*- coding: utf-8 -*-
"""
WebSocket 实时推送

向前端推送实时转写文本和建议。
"""

import json
import logging
from datetime import datetime
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# 活跃的 WebSocket 连接
_active_connections: Set[WebSocket] = set()


async def broadcast_transcript(data: dict):
    """广播转写结果到所有连接"""
    message = json.dumps(data, ensure_ascii=False, default=str)
    disconnected = set()
    for ws in _active_connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    _active_connections.difference_update(disconnected)


async def broadcast_suggestion(data: dict):
    """广播建议到所有连接"""
    message = json.dumps(data, ensure_ascii=False, default=str)
    disconnected = set()
    for ws in _active_connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    _active_connections.difference_update(disconnected)


@router.websocket("/ws/meeting")
async def meeting_websocket(websocket: WebSocket):
    """
    会议实时推送 WebSocket 端点。

    连接后自动接收：
    - {"type": "transcript", "speaker": "interviewer"|"self", "text": "...", "timestamp": "..."}
    - {"type": "suggestion", "content": "...", "timestamp": "..."}
    """
    await websocket.accept()
    _active_connections.add(websocket)
    logger.info(f"WebSocket 已连接: {websocket.client}")

    try:
        while True:
            # 保持连接，接收客户端消息（如心跳）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        logger.info(f"WebSocket 已断开: {websocket.client}")
    finally:
        _active_connections.discard(websocket)


def setup_ws_callbacks(transcriber, suggestion_engine):
    """设置 WebSocket 广播回调"""

    def on_transcript(segment):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            data = {
                "type": "transcript",
                "speaker": segment.speaker.value,
                "text": segment.text,
                "timestamp": segment.timestamp.isoformat(),
                "language": segment.language,
            }
            if loop.is_running():
                asyncio.ensure_future(broadcast_transcript(data))
        except Exception as e:
            logger.error(f"广播转写失败: {e}")

    def on_suggestion(suggestion):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            data = {
                "type": "suggestion",
                "content": suggestion.content,
                "timestamp": suggestion.timestamp.isoformat(),
            }
            if loop.is_running():
                asyncio.ensure_future(broadcast_suggestion(data))
        except Exception as e:
            logger.error(f"广播建议失败: {e}")

    transcriber.set_transcript_callback(on_transcript)
    suggestion_engine.set_suggestion_callback(on_suggestion)
