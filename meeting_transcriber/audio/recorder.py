# -*- coding: utf-8 -*-
"""
录音会话管理器

控制录音生命周期，管理音频分段和回调。
"""

import logging
import uuid
from datetime import datetime

from ..models import AudioSegment, MeetingSession, MeetingScene, SpeakerLabel
from ..config import meeting_config
from .capture import AudioCapture
from .device_manager import get_device_manager, AudioDeviceInfo

logger = logging.getLogger(__name__)


class Recorder:
    """录音会话管理器"""

    def __init__(self):
        self._session: MeetingSession | None = None
        self._capture: AudioCapture | None = None
        self._on_segment_callback = None

    @property
    def session(self) -> MeetingSession | None:
        return self._session

    def start(
        self,
        scene: MeetingScene = MeetingScene.INTERVIEW,
        mic_device_index: int | None = None,
        loopback_device_index: int | None = None,
        chunk_duration: float | None = None,
    ) -> MeetingSession:
        """开始录制"""
        if self._session and self._session.is_running:
            raise RuntimeError("已有录制会话正在进行中")

        if chunk_duration:
            meeting_config.audio_chunk_duration = chunk_duration

        dm = get_device_manager()

        mic_device: AudioDeviceInfo | None = None
        if mic_device_index is not None:
            mic_device = dm.get_device_by_index(mic_device_index)
            if not mic_device:
                raise ValueError(f"麦克风设备索引 {mic_device_index} 无效")

        loopback_device: AudioDeviceInfo | None = None
        if loopback_device_index is not None:
            loopback_device = dm.get_device_by_index(loopback_device_index)
            if not loopback_device:
                raise ValueError(f"Loopback 设备索引 {loopback_device_index} 无效")

        session_id = str(uuid.uuid4())[:8]
        self._session = MeetingSession(
            session_id=session_id,
            scene=scene,
            start_time=datetime.now(),
            is_running=True,
        )

        self._capture = AudioCapture(
            mic_device=mic_device,
            loopback_device=loopback_device,
        )
        self._capture.set_chunk_callback(self._on_chunk)
        self._capture.start()

        # 流式 ASR 模式
        if meeting_config.asr_mode == "streaming":
            from ..asr.transcriber import Transcriber
            # 流式模式下，音频帧直接推给 ASR，不切 WAV
            self._capture.set_stream_callback(self._on_stream_frame)
            logger.info("录音模式: 流式 ASR")
        else:
            logger.info("录音模式: 批量 ASR (Gradio)")

        logger.info(f"录制已开始: session={session_id}, scene={scene.value}")
        return self._session

    def stop(self) -> MeetingSession | None:
        """停止录制"""
        if not self._session or not self._session.is_running:
            return None

        self._capture.stop()

        # 流式 ASR 模式清理
        if meeting_config.asr_mode == "streaming" and hasattr(self, '_transcriber_ref') and self._transcriber_ref:
            self._transcriber_ref.stop_streaming()

        self._session.is_running = False
        self._session.end_time = datetime.now()

        logger.info(f"录制已停止: session={self._session.session_id}")
        return self._session

    def _on_chunk(self, segment: AudioSegment):
        """音频分段回调"""
        if self._session:
            segment.session_id = self._session.session_id

        if self._on_segment_callback:
            self._on_segment_callback(segment)

    def set_segment_callback(self, callback):
        """设置音频分段回调"""
        self._on_segment_callback = callback

    def set_transcriber(self, transcriber):
        """设置 Transcriber 引用（流式模式需要）"""
        self._transcriber_ref = transcriber

    def _on_stream_frame(self, speaker, pcm_data: bytes):
        """流式模式：将 PCM 帧直接推给 ASR"""
        if hasattr(self, '_transcriber_ref') and self._transcriber_ref:
            self._transcriber_ref.send_stream_audio(speaker, pcm_data)
