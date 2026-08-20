# -*- coding: utf-8 -*-
"""
全局配置

通过环境变量或 .env 文件加载配置项。
"""

import os
from dotenv import load_dotenv

load_dotenv()


class MeetingConfig:
    """会议转写系统配置"""

    # ── ASR 服务配置 ──────────────────────────────────────────────────────
    asr_server_url: str = os.getenv("ASR_SERVER_URL", "http://10.12.218.20:8101")
    asr_language: str = os.getenv("ASR_LANGUAGE", "Auto")  # 语言参数，Auto 为自动检测

    # ── 音频配置 ──────────────────────────────────────────────────────────
    audio_sample_rate: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))  # 统一采样率
    audio_channels: int = int(os.getenv("AUDIO_CHANNELS", "1"))  # 单声道
    audio_chunk_duration: float = float(os.getenv("AUDIO_CHUNK_DURATION", "4.0"))  # 分段时长（秒）
    audio_format: str = "wav"

    # ── LLM 建议配置 ──────────────────────────────────────────────────────
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    suggestion_model: str = os.getenv("SUGGESTION_MODEL", "deepseek-v4-pro")
    suggestion_min_interval: float = float(os.getenv("SUGGESTION_MIN_INTERVAL", "15.0"))  # 最小建议间隔（秒）
    suggestion_time_trigger: float = float(os.getenv("SUGGESTION_TIME_TRIGGER", "45.0"))  # 定时触发间隔（秒）
    suggestion_context_rounds: int = int(os.getenv("SUGGESTION_CONTEXT_ROUNDS", "10"))  # 上下文窗口轮数

    # ── 报告配置 ──────────────────────────────────────────────────────────
    report_output_dir: str = os.getenv("REPORT_OUTPUT_DIR", "./meeting_reports")

    # ── ASR 模式配置 ──────────────────────────────────────────────────────
    asr_mode: str = os.getenv("ASR_MODE", "batch")  # "batch" 或 "streaming"

    # ── FastAPI 配置 ──────────────────────────────────────────────────────
    host: str = os.getenv("MEETING_HOST", "0.0.0.0")
    port: int = int(os.getenv("MEETING_PORT", "8200"))
    debug: bool = os.getenv("MEETING_DEBUG", "false").lower() == "true"


meeting_config = MeetingConfig()
