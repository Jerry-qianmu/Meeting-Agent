# -*- coding: utf-8 -*-
"""
ASR 编排器

管理双流音频的 ASR 识别，按时间戳合并结果。
"""

import asyncio
import logging
import heapq
from datetime import datetime

from ..models import AudioSegment, TranscriptSegment, SpeakerLabel
from ..config import meeting_config
from .gradio_asr import get_gradio_asr

logger = logging.getLogger(__name__)


class Transcriber:
    """ASR 编排器"""

    def __init__(self):
        self._asr = get_gradio_asr()
        self._on_transcript_callback = None
        self._pending_tasks: list[asyncio.Task] = []

    async def process_segment(self, segment: AudioSegment):
        """
        处理一个音频片段：调用 ASR 并回调结果。

        Args:
            segment: 音频片段
        """
        if not segment.data_path:
            logger.warning(f"音频片段无数据路径，跳过: {segment.speaker}")
            return

        task = asyncio.create_task(self._recognize_and_callback(segment))
        self._pending_tasks.append(task)
        task.add_done_callback(lambda t: self._pending_tasks.discard(t) if hasattr(self._pending_tasks, 'discard') else None)

    async def _recognize_and_callback(self, segment: AudioSegment):
        """识别单个音频片段"""
        try:
            lang, text = await self._asr.transcribe(segment.data_path)

            if not text or not text.strip():
                logger.debug(f"ASR 返回空文本，跳过: {segment.speaker.value}")
                return

            transcript = TranscriptSegment(
                session_id=segment.session_id,
                speaker=segment.speaker,
                timestamp=segment.timestamp,
                text=text.strip(),
                language=lang,
                audio_duration=segment.duration,
            )

            if self._on_transcript_callback:
                self._on_transcript_callback(transcript)

            logger.info(f"[{segment.speaker.value}] {text.strip()[:80]}")

        except Exception as e:
            logger.error(f"ASR 处理失败: {e}")

    async def wait_pending(self):
        """等待所有待处理任务完成"""
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
            self._pending_tasks.clear()

    def set_transcript_callback(self, callback):
        """设置转写结果回调"""
        self._on_transcript_callback = callback

    def start_streaming(self, session_id: str = ""):
        """启动流式 ASR 模式"""
        from .streaming_asr import get_streaming_asr_manager
        self._streaming_manager = get_streaming_asr_manager()
        self._streaming_manager.set_transcript_callback(self._on_transcript_callback)
        self._streaming_manager.start(session_id)
        logger.info("流式 ASR 模式已启动")

    def stop_streaming(self):
        """停止流式 ASR 模式"""
        if hasattr(self, '_streaming_manager') and self._streaming_manager:
            self._streaming_manager.stop()
            logger.info("流式 ASR 模式已停止")

    def send_stream_audio(self, speaker: SpeakerLabel, pcm_data: bytes):
        """发送音频帧到流式 ASR"""
        if hasattr(self, '_streaming_manager') and self._streaming_manager:
            if speaker == SpeakerLabel.SELF:
                self._streaming_manager.send_mic_audio(pcm_data)
            else:
                self._streaming_manager.send_loopback_audio(pcm_data)
