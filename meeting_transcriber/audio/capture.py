# -*- coding: utf-8 -*-
"""
双流音频捕获

同时捕获 WASAPI Loopback（系统音频输出 → 面试官声音）
和麦克风输入（用户声音）。
"""

import io
import logging
import tempfile
import threading
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from ..models import AudioSegment, SpeakerLabel
from ..config import meeting_config
from .device_manager import get_device_manager, AudioDeviceInfo

logger = logging.getLogger(__name__)

# VAD 配置：麦克风语音活动检测
# 根据实测：静音 RMS<50, 人声 RMS 200-500, 耳机漏拾 RMS 50-100
VAD_SPEECH_START = 120    # RMS 超过此值 → 判定为语音开始
VAD_SPEECH_STOP = 80      # RMS 低于此值 → 判定为语音结束
VAD_HANGOVER_FRAMES = 15  # 语音结束后保持的帧数（约 0.5 秒），避免说话间隙断开
# 交叉通道检测：麦克风 RMS / Loopback RMS 低于此比例 → 判定为耳机漏拾
VAD_CROSS_CHANNEL_RATIO = 0.6


class AudioCapture:
    """双流音频捕获器"""

    def __init__(
        self,
        mic_device: AudioDeviceInfo | None = None,
        loopback_device: AudioDeviceInfo | None = None,
        sample_rate: int | None = None,
    ):
        self._sample_rate = sample_rate or meeting_config.audio_sample_rate
        self._running = False
        self._lock = threading.Lock()

        dm = get_device_manager()
        self._mic_device = mic_device or dm.auto_select_microphone()
        self._loopback_device = loopback_device or dm.auto_select_loopback()

        if not self._mic_device:
            raise RuntimeError("未找到麦克风设备")
        if not self._loopback_device:
            logger.warning("未找到 WASAPI Loopback 设备，将仅使用麦克风")

        self._mic_stream = None
        self._loopback_stream = None
        self._pyaudio_instance = None
        self._on_stream_callback = None
        self._on_chunk_callback = None

        # VAD 状态（麦克风通道）
        self._vad_speech_active = False
        self._vad_hangover = 0
        # Loopback 能量追踪（用于交叉通道检测）
        self._loopback_rms_window: list[float] = []
        self._loopback_rms_idx = 0
        self._loopback_window_ready = False  # loopback 窗口是否已填充足够数据

        logger.info(f"音频捕获器初始化: 麦克风=[{self._mic_device.index}] {self._mic_device.name}")
        logger.info(f"音频捕获器初始化: Loopback=[{self._loopback_device.index}] {self._loopback_device.name}")

    def start(self):
        """开始捕获音频"""
        if self._running:
            return

        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            import pyaudio

        self._pyaudio_module = pyaudio  # 保存模块引用，子线程需要访问 paInt16 等常量
        self._pyaudio_instance = pyaudio.PyAudio()
        self._running = True

        # 启动麦克风捕获线程
        self._mic_thread = threading.Thread(target=self._capture_mic, daemon=True)
        self._mic_thread.start()

        # 启动 Loopback 捕获线程（如果有设备）
        if self._loopback_device:
            self._loopback_thread = threading.Thread(target=self._capture_loopback, daemon=True)
            self._loopback_thread.start()

        logger.info("音频捕获已启动")

    def stop(self):
        """停止捕获

        先设置标志让线程自行退出，再等待线程结束后才 terminate pyaudio，
        避免 Windows WASAPI 下 terminate 与正在 read 的线程冲突导致 segfault。
        """
        self._running = False

        # 停止流（会中断阻塞中的 stream.read）
        if self._mic_stream:
            try:
                self._mic_stream.stop_stream()
            except Exception:
                pass
        if self._loopback_stream:
            try:
                self._loopback_stream.stop_stream()
            except Exception:
                pass

        # 等待捕获线程退出（最多 3 秒）
        threads = []
        if hasattr(self, '_mic_thread') and self._mic_thread.is_alive():
            threads.append(self._mic_thread)
        if hasattr(self, '_loopback_thread') and self._loopback_thread.is_alive():
            threads.append(self._loopback_thread)
        for t in threads:
            t.join(timeout=3)

        # 线程退出后再关闭流和 terminate
        if self._mic_stream:
            try:
                self._mic_stream.close()
            except Exception:
                pass
        if self._loopback_stream:
            try:
                self._loopback_stream.close()
            except Exception:
                pass
        if self._pyaudio_instance:
            try:
                self._pyaudio_instance.terminate()
            except Exception:
                pass
        logger.info("音频捕获已停止")

    def _capture_mic(self):
        """捕获麦克风音频

        使用设备原生参数打开，避免强制采样率导致静音。
        后续在 _read_audio_loop 中统一转换为 16kHz 单声道。
        """
        pa = self._pyaudio_instance
        # 使用设备原生参数，避免部分声卡不支持重采样导致静音
        device_rate = int(self._mic_device.sample_rate)
        device_channels = max(self._mic_device.max_input_channels, 1)
        try:
            self._mic_stream = pa.open(
                format=self._pyaudio_module.paInt16,
                channels=device_channels,
                rate=device_rate,
                input=True,
                input_device_index=self._mic_device.index,
                frames_per_buffer=1024,
            )
        except Exception as e:
            logger.error(f"打开麦克风失败: {e}")
            self._running = False
            return

        logger.info(f"麦克风捕获线程已启动 (原生参数: {device_rate}Hz, {device_channels}ch)")
        self._read_audio_loop(
            self._mic_stream, SpeakerLabel.SELF, "mic",
            stream_rate=device_rate, stream_channels=device_channels,
        )
        logger.info("麦克风捕获线程已结束")

    def _capture_loopback(self):
        """捕获系统音频（Loopback）"""
        pa = self._pyaudio_instance
        # Loopback 必须用设备原生参数打开，否则会严重失真
        device_rate = int(self._loopback_device.sample_rate)
        device_channels = max(self._loopback_device.max_input_channels, 2)
        try:
            self._loopback_stream = pa.open(
                format=self._pyaudio_module.paInt16,
                channels=device_channels,
                rate=device_rate,
                input=True,
                input_device_index=self._loopback_device.index,
                frames_per_buffer=1024,
            )
        except Exception as e:
            logger.error(f"打开 Loopback 设备失败: {e}")
            self._running = False
            return

        logger.info(f"Loopback 捕获线程已启动 (原生参数: {device_rate}Hz, {device_channels}ch)")
        self._read_audio_loop(
            self._loopback_stream, SpeakerLabel.INTERVIEWER, "loopback",
            stream_rate=device_rate, stream_channels=device_channels,
        )
        logger.info("Loopback 捕获线程已结束")

    def _read_audio_loop(self, stream, speaker: SpeakerLabel, tag: str,
                         stream_rate: int | None = None, stream_channels: int | None = None):
        """
        持续读取音频数据，按分段时长切片并写入临时文件。

        Args:
            stream_rate: 流的采样率（Loopback 可能与目标不同）
            stream_channels: 流的声道数（Loopback 可能是立体声）
        """
        rate = stream_rate or self._sample_rate
        channels = stream_channels or 1
        chunk_seconds = meeting_config.audio_chunk_duration
        frames_per_chunk = int(rate * chunk_seconds)
        frame_size = 2  # int16 = 2 bytes per sample

        buffer: list[bytes] = []
        total_frames = 0

        while self._running:
            try:
                data = stream.read(1024, exception_on_overflow=False)
                # 流式模式：直接推送 PCM 帧（麦克风通道会做 VAD 过滤）
                if self._on_stream_callback:
                    pcm = self._convert_to_pcm16k_mono(data, rate, channels, speaker=speaker)
                    if pcm:
                        self._on_stream_callback(speaker, pcm)
                buffer.append(data)
                total_frames += len(data) // frame_size

                if total_frames >= frames_per_chunk:
                    self._flush_chunk(buffer, speaker, tag, total_frames,
                                      stream_rate=rate, stream_channels=channels)
                    buffer = []
                    total_frames = 0
            except Exception as e:
                if self._running:
                    logger.error(f"[{tag}] 音频读取错误: {e}")
                break

        # 刷出剩余数据
        if buffer and total_frames > 0:
            self._flush_chunk(buffer, speaker, tag, total_frames,
                              stream_rate=rate, stream_channels=channels)

    def _flush_chunk(self, buffer: list[bytes], speaker: SpeakerLabel, tag: str,
                     total_frames: int, stream_rate: int | None = None,
                     stream_channels: int | None = None):
        """
        将缓冲区数据写入临时 WAV 文件并回调。
        如果流参数与目标参数不同，会自动重采样和转换声道。
        """
        raw_data = b"".join(buffer)
        rate = stream_rate or self._sample_rate
        channels = stream_channels or 1
        duration = total_frames / rate

        # 转换为 numpy 进行处理
        audio = np.frombuffer(raw_data, dtype=np.int16)

        # 多声道 → 单声道（取平均）
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)

        # VAD：麦克风通道做能量检测，低能量跳过（batch 模式用简单阈值 + 交叉通道）
        if speaker == SpeakerLabel.SELF:
            rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))

            # 启动保护
            if not self._loopback_window_ready and self._loopback_rms_window:
                avg_lb_rms = np.mean(self._loopback_rms_window)
                if avg_lb_rms > 100 and rms < avg_lb_rms:
                    logger.info(f"[{tag}] VAD: 启动保护过滤 (mic={rms:.0f} lb_avg={avg_lb_rms:.0f})")
                    return

            # 交叉通道检测
            if self._loopback_window_ready and self._loopback_rms_window:
                avg_lb_rms = np.mean(self._loopback_rms_window)
                if avg_lb_rms > 200 and rms > 0:
                    ratio = rms / avg_lb_rms
                    if ratio < VAD_CROSS_CHANNEL_RATIO:
                        logger.info(f"[{tag}] VAD: 交叉通道过滤 (mic={rms:.0f} lb={avg_lb_rms:.0f} ratio={ratio:.2f})")
                        return

            if rms < VAD_SPEECH_STOP:
                logger.info(f"[{tag}] VAD: 跳过低能量段 (RMS={rms:.0f}, 阈值={VAD_SPEECH_STOP})")
                return
            else:
                logger.info(f"[{tag}] VAD: 通过 (RMS={rms:.0f})")
        else:
            # Loopback 通道：追踪能量
            rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
            if len(self._loopback_rms_window) < 20:
                self._loopback_rms_window.append(rms)
                if len(self._loopback_rms_window) >= 20:
                    self._loopback_window_ready = True
            else:
                self._loopback_rms_window[self._loopback_rms_idx % 20] = rms
            self._loopback_rms_idx += 1

        # 重采样到目标采样率
        if rate != self._sample_rate:
            ratio = self._sample_rate / rate
            new_length = int(len(audio) * ratio)
            indices = np.linspace(0, len(audio) - 1, new_length).astype(int)
            audio = audio[indices].astype(np.int16)

        # 写入临时 WAV 文件（目标参数：16000Hz 单声道）
        tmp_dir = Path(tempfile.gettempdir()) / "meeting_audio"
        tmp_dir.mkdir(exist_ok=True)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        tmp_path = tmp_dir / f"{tag}_{ts_str}.wav"

        with wave.open(str(tmp_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(audio.tobytes())

        segment = AudioSegment(
            session_id="",  # 由 recorder 填充
            speaker=speaker,
            timestamp=datetime.now(),
            duration=duration,
            sample_rate=self._sample_rate,
            data_path=str(tmp_path),
        )

        # 通过回调通知上层
        if self._on_chunk_callback:
            self._on_chunk_callback(segment)

    def _convert_to_pcm16k_mono(self, raw_data: bytes, src_rate: int,
                                 src_channels: int, speaker: SpeakerLabel | None = None) -> bytes | None:
        """将原始音频数据转换为 16kHz 单声道 int16 PCM

        对麦克风通道做 VAD：使用双阈值 + 保持时间 + 交叉通道检测，
        避免麦克风漏拾耳机声音导致角色误判，同时不切断正常说话。
        """
        if not raw_data:
            return None

        audio = np.frombuffer(raw_data, dtype=np.int16)

        # 多声道 → 单声道
        if src_channels > 1:
            audio = audio.reshape(-1, src_channels).mean(axis=1).astype(np.int16)

        rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))

        # Loopback 通道：追踪能量用于交叉通道检测
        if speaker == SpeakerLabel.INTERVIEWER:
            if len(self._loopback_rms_window) < 20:
                self._loopback_rms_window.append(rms)
                if len(self._loopback_rms_window) >= 20:
                    self._loopback_window_ready = True
            else:
                self._loopback_rms_window[self._loopback_rms_idx % 20] = rms
            self._loopback_rms_idx += 1

        # VAD：麦克风通道使用状态机检测语音 + 交叉通道过滤
        if speaker == SpeakerLabel.SELF:
            # 启动保护：Loopback 窗口未就绪时，如果 Loopback 已有数据（说明有系统音频），
            # 麦克风需要更高能量才能通过，防止启动阶段漏拾
            if not self._loopback_window_ready and self._loopback_rms_window:
                avg_lb_rms = np.mean(self._loopback_rms_window)
                if avg_lb_rms > 100 and rms < avg_lb_rms:
                    logger.debug(f"[VAD] 启动保护: 跳过 (mic={rms:.0f} lb_avg={avg_lb_rms:.0f})")
                    return None

            # 交叉通道检测：如果 Loopback 同时有声音，且麦克风能量相对较低
            # → 大概率是耳机漏拾，不是用户在说话
            if self._loopback_window_ready and self._loopback_rms_window:
                avg_lb_rms = np.mean(self._loopback_rms_window)
                if avg_lb_rms > 200 and rms > 0:
                    ratio = rms / avg_lb_rms
                    if ratio < VAD_CROSS_CHANNEL_RATIO:
                        # 麦克风能量远低于 Loopback → 耳机漏拾
                        self._vad_speech_active = False
                        self._vad_hangover = 0
                        logger.debug(f"[VAD] 交叉通道过滤: mic={rms:.0f} lb={avg_lb_rms:.0f} ratio={ratio:.2f}")
                        return None

            if self._vad_speech_active:
                # 语音进行中
                if rms >= VAD_SPEECH_STOP:
                    # 仍在说话，重置保持计数
                    self._vad_hangover = VAD_HANGOVER_FRAMES
                else:
                    # 能量下降，倒计时
                    self._vad_hangover -= 1
                    if self._vad_hangover <= 0:
                        # 保持时间结束，判定为语音结束
                        self._vad_speech_active = False
                        logger.debug(f"[VAD] 语音结束 RMS={rms:.0f}")
            else:
                # 非语音状态
                if rms >= VAD_SPEECH_START:
                    # 检测到语音，开始
                    self._vad_speech_active = True
                    self._vad_hangover = VAD_HANGOVER_FRAMES
                    logger.info(f"[VAD] 语音开始 RMS={rms:.0f}")
                else:
                    # 仍在静音
                    return None

        # 重采样到 16kHz
        if src_rate != self._sample_rate:
            ratio = self._sample_rate / src_rate
            new_length = int(len(audio) * ratio)
            indices = np.linspace(0, len(audio) - 1, new_length).astype(int)
            audio = audio[indices].astype(np.int16)

        return audio.tobytes()

    def set_chunk_callback(self, callback):
        """设置分段回调函数"""
        self._on_chunk_callback = callback

    def set_stream_callback(self, callback):
        """设置流式音频帧回调（用于流式 ASR 模式）"""
        self._on_stream_callback = callback
