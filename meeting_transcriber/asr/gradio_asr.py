# -*- coding: utf-8 -*-
"""
Gradio ASR 服务封装

通过 gradio_client 调用本地部署的 ASR 模型服务。
"""

import asyncio
import logging
from pathlib import Path

from gradio_client import Client, handle_file

from ..config import meeting_config

logger = logging.getLogger(__name__)


class GradioASR:
    """Gradio ASR 客户端"""

    def __init__(self, server_url: str | None = None):
        self._server_url = server_url or meeting_config.asr_server_url
        self._client: Client | None = None
        self._lock = asyncio.Lock()  # 串行化 ASR 请求

    def init_client(self):
        """初始化 Client（录制开始时调用一次）"""
        if self._client is None:
            logger.info(f"连接 ASR 服务: {self._server_url}")
            self._client = Client(self._server_url)
            logger.info("ASR 服务连接成功")

    def close_client(self):
        """关闭 Client（录制结束时调用）"""
        self._client = None

    async def transcribe(self, audio_path: str, language: str | None = None) -> tuple[str, str]:
        """
        异步识别音频文件。

        使用 asyncio.Lock 串行化请求，确保同一时刻只有一个 ASR 请求在执行，
        避免共享 Client 的线程安全问题和请求交错。

        Args:
            audio_path: 音频文件路径（WAV 格式）
            language: 语言参数，默认使用配置中的值

        Returns:
            (语言, 识别文本) 元组
        """
        lang = language or meeting_config.asr_language
        async with self._lock:
            result = await asyncio.to_thread(self._sync_transcribe, audio_path, lang)
            return result

    def _sync_transcribe(self, audio_path: str, language: str) -> tuple[str, str]:
        """同步识别（在 asyncio.Lock 保护下执行，线程安全）"""
        try:
            self.init_client()
            result = self._client.predict(
                audio_upload=handle_file(audio_path),
                lang_disp=language,
                api_name="/run",
            )
            # result 是元组: (语言, 识别文本)
            if isinstance(result, (tuple, list)) and len(result) >= 2:
                detected_lang = str(result[0])
                text = str(result[1])
            else:
                detected_lang = language
                text = str(result)

            logger.debug(f"ASR 结果: lang={detected_lang}, text={text[:50]}...")
            return detected_lang, text

        except Exception as e:
            logger.error(f"ASR 识别失败: {e}")
            return ("", "")

    async def health_check(self) -> bool:
        """检查 ASR 服务是否可用"""
        try:
            self.init_client()
            return True
        except Exception as e:
            logger.error(f"ASR 服务不可用: {e}")
            return False


# 全局单例
_asr_instance: GradioASR | None = None


def get_gradio_asr() -> GradioASR:
    """获取 GradioASR 单例"""
    global _asr_instance
    if _asr_instance is None:
        _asr_instance = GradioASR()
    return _asr_instance
