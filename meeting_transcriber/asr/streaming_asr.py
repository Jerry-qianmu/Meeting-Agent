# -*- coding: utf-8 -*-
"""
DashScope Paraformer 流式 ASR

使用 paraformer-realtime-v2 模型实现真正的流式语音识别。
音频边录边识别，逐句返回结果，延迟 <1秒。
"""

import asyncio
import logging
import threading
from datetime import datetime

import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

from ..models import TranscriptSegment, SpeakerLabel
from ..config import meeting_config

logger = logging.getLogger(__name__)


class StreamingASRSession:
    """
    单路流式 ASR 会话。

    维护一个与 DashScope Paraformer 的 WebSocket 连接，
    持续接收 PCM 音频帧并实时返回识别结果。
    """

    def __init__(self, speaker: SpeakerLabel, on_transcript_callback=None):
        """
        Args:
            speaker: 说话人标记（SELF 或 INTERVIEWER）
            on_transcript_callback: 转写结果回调函数
        """
        self._speaker = speaker
        self._callback_fn = on_transcript_callback
        self._recognition: Recognition | None = None
        self._running = False
        self._lock = threading.Lock()

        # 回调实现
        self._callback = _ASRCallback(speaker, on_transcript_callback)

    def start(self):
        """启动流式识别会话"""
        if self._running:
            return

        dashscope.api_key = meeting_config.dashscope_api_key

        self._recognition = Recognition(
            model="paraformer-realtime-v2",
            format="pcm",
            sample_rate=meeting_config.audio_sample_rate,
            language_hints=["zh", "en"],
            callback=self._callback,
        )

        self._recognition.start()
        self._running = True
        logger.info(f"流式 ASR 会话已启动: {self._speaker.value}")

    def send_audio(self, pcm_data: bytes):
        """
        发送 PCM 音频帧。

        Args:
            pcm_data: 16kHz 单声道 int16 PCM 数据，建议每次 100ms（3200 bytes）
        """
        if not self._running or not self._recognition:
            return
        try:
            self._recognition.send_audio_frame(pcm_data)
        except Exception as e:
            logger.error(f"[{self._speaker.value}] 发送音频失败: {e}")

    def stop(self):
        """停止流式识别"""
        if not self._running:
            return

        self._running = False
        if self._recognition:
            try:
                self._recognition.stop()
            except Exception as e:
                logger.error(f"[{self._speaker.value}] 停止 ASR 失败: {e}")
            self._recognition = None

        logger.info(f"流式 ASR 会话已停止: {self._speaker.value}")

    @property
    def is_running(self) -> bool:
        return self._running


class _ASRCallback(RecognitionCallback):
    """Paraformer 回调实现"""

    def __init__(self, speaker: SpeakerLabel, on_transcript_callback):
        self._speaker = speaker
        self._callback_fn = on_transcript_callback
        self._current_text = ""
        self._session_id = ""

    def on_open(self) -> None:
        logger.info(f"[{self._speaker.value}] ASR 连接已建立")

    def on_close(self) -> None:
        logger.info(f"[{self._speaker.value}] ASR 连接已关闭")

    def on_complete(self) -> None:
        logger.info(f"[{self._speaker.value}] ASR 识别完成")

    def on_error(self, message) -> None:
        logger.error(f"[{self._speaker.value}] ASR 错误: {message.message if hasattr(message, 'message') else message}")

    def on_event(self, result: RecognitionResult) -> None:
        """收到识别结果"""
        try:
            sentence = result.get_sentence()
            if not sentence or "text" not in sentence:
                return

            text = sentence["text"]
            if not text.strip():
                return

            is_final = RecognitionResult.is_sentence_end(sentence)

            segment = TranscriptSegment(
                session_id=self._session_id,
                speaker=self._speaker,
                timestamp=datetime.now(),
                text=text.strip(),
                language=sentence.get("language", ""),
                audio_duration=sentence.get("duration", 0) / 1000.0,
                is_final=is_final,
            )

            if self._callback_fn:
                self._callback_fn(segment)

            if is_final:
                logger.info(f"[{self._speaker.value}] {text.strip()[:80]}")
            else:
                logger.debug(f"[{self._speaker.value}] 识别中: {text[:50]}...")

        except Exception as e:
            logger.error(f"处理 ASR 结果失败: {e}")

    def set_session_id(self, session_id: str):
        self._session_id = session_id


class StreamingASRManager:
    """
    流式 ASR 管理器。

    管理两路流式 ASR 会话（麦克风 + Loopback），
    提供统一的启动/停止/发送接口。
    """

    def __init__(self):
        self._mic_session: StreamingASRSession | None = None
        self._loopback_session: StreamingASRSession | None = None
        self._on_transcript_callback = None

    def start(self, session_id: str = ""):
        """启动两路流式 ASR"""
        self._mic_session = StreamingASRSession(
            speaker=SpeakerLabel.SELF,
            on_transcript_callback=self._on_transcript_callback,
        )
        self._loopback_session = StreamingASRSession(
            speaker=SpeakerLabel.INTERVIEWER,
            on_transcript_callback=self._on_transcript_callback,
        )

        self._mic_session._callback.set_session_id(session_id)
        self._loopback_session._callback.set_session_id(session_id)

        self._mic_session.start()
        self._loopback_session.start()

    def stop(self):
        """停止两路流式 ASR"""
        if self._mic_session:
            self._mic_session.stop()
        if self._loopback_session:
            self._loopback_session.stop()

    def send_mic_audio(self, pcm_data: bytes):
        """发送麦克风音频帧"""
        if self._mic_session:
            self._mic_session.send_audio(pcm_data)

    def send_loopback_audio(self, pcm_data: bytes):
        """发送 Loopback 音频帧"""
        if self._loopback_session:
            self._loopback_session.send_audio(pcm_data)

    def set_transcript_callback(self, callback):
        """设置转写结果回调"""
        self._on_transcript_callback = callback


# 全局单例
_streaming_asr_manager: StreamingASRManager | None = None


def get_streaming_asr_manager() -> StreamingASRManager:
    """获取 StreamingASRManager 单例"""
    global _streaming_asr_manager
    if _streaming_asr_manager is None:
        _streaming_asr_manager = StreamingASRManager()
    return _streaming_asr_manager
