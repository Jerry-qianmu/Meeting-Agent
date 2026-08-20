# -*- coding: utf-8 -*-
"""
REST API 路由

提供会议录制的启动、停止、状态查询和报告获取接口。
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..models import MeetingStartRequest, MeetingStatusResponse, MeetingSession
from ..audio.recorder import Recorder
from ..asr.transcriber import Transcriber
from ..advisor.suggestion_engine import SuggestionEngine
from ..report.markdown_writer import MarkdownWriter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meeting", tags=["会议转写"])

# 全局状态
_recorder = Recorder()
_transcriber = Transcriber()
_suggestion_engine = SuggestionEngine()
_markdown_writer = MarkdownWriter()
_current_session: MeetingSession | None = None


def _on_audio_segment(segment):
    """音频分段回调：交给 ASR 处理"""
    import asyncio
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.ensure_future(_transcriber.process_segment(segment))


def _on_transcript(transcript):
    """转写结果回调：更新会话 + 触发建议 + 写入报告"""
    if _current_session:
        _current_session.transcripts.append(transcript)

    _suggestion_engine.add_transcript(transcript)
    _markdown_writer.write_transcript(transcript)


def _on_suggestion(suggestion):
    """建议回调：更新会话 + 写入报告"""
    if _current_session:
        _current_session.suggestions.append(suggestion)

    _markdown_writer.write_suggestion(suggestion)


# 设置回调
_recorder.set_segment_callback(_on_audio_segment)
_transcriber.set_transcript_callback(_on_transcript)
_suggestion_engine.set_suggestion_callback(_on_suggestion)


@router.post("/start", summary="开始录制")
async def start_meeting(request: MeetingStartRequest):
    """开始会议录制"""
    global _current_session

    if _current_session and _current_session.is_running:
        raise HTTPException(status_code=400, detail="已有录制会话正在进行中")

    try:
        _suggestion_engine.set_scene(request.scene)
        _suggestion_engine.clear()

        session = _recorder.start(
            scene=request.scene,
            mic_device_index=request.mic_device_index,
            loopback_device_index=request.loopback_device_index,
            chunk_duration=request.chunk_duration,
        )

        _current_session = session
        _markdown_writer.start(session)

        return {
            "status": "started",
            "session_id": session.session_id,
            "scene": session.scene.value,
            "start_time": session.start_time.isoformat() if session.start_time else None,
        }

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stop", summary="停止录制")
async def stop_meeting():
    """停止会议录制并生成报告"""
    global _current_session

    if not _current_session or not _current_session.is_running:
        raise HTTPException(status_code=400, detail="当前没有进行中的录制")

    session = _recorder.stop()
    if session:
        _markdown_writer.finish(session)

    # 关闭 ASR Client
    from ..asr.gradio_asr import get_gradio_asr
    get_gradio_asr().close_client()

    result = {
        "status": "stopped",
        "session_id": session.session_id if session else None,
        "transcript_count": len(session.transcripts) if session else 0,
        "suggestion_count": len(session.suggestions) if session else 0,
        "report_path": session.report_path if session else None,
    }

    _current_session = None
    return result


@router.get("/status", summary="获取录制状态")
async def get_status():
    """获取当前录制状态"""
    if not _current_session:
        return MeetingStatusResponse(
            session_id="",
            is_running=False,
            scene="",
        )

    elapsed = 0.0
    if _current_session.start_time:
        elapsed = (datetime.now() - _current_session.start_time).total_seconds()

    return MeetingStatusResponse(
        session_id=_current_session.session_id,
        is_running=_current_session.is_running,
        scene=_current_session.scene.value,
        start_time=_current_session.start_time.isoformat() if _current_session.start_time else None,
        transcript_count=len(_current_session.transcripts),
        suggestion_count=len(_current_session.suggestions),
        elapsed_seconds=elapsed,
    )


@router.get("/devices", summary="列出音频设备")
async def list_devices():
    """列出可用的音频设备"""
    from ..audio.device_manager import get_device_manager
    dm = get_device_manager()

    return {
        "loopback_devices": [
            {"index": d.index, "name": d.name, "sample_rate": d.sample_rate}
            for d in dm.get_loopback_devices()
        ],
        "microphone_devices": [
            {"index": d.index, "name": d.name, "sample_rate": d.sample_rate}
            for d in dm.get_microphone_devices()
        ],
    }
