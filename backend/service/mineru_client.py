# -*- coding: utf-8 -*-
"""
MinerU HTTP API 客户端
调用 MinerU 服务将 PDF 转换为 Markdown
"""

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class MinerUClient:
    """MinerU HTTP API 客户端"""

    def __init__(self, api_url: str = "http://localhost:8888", timeout: int = 300):
        """
        Args:
            api_url: MinerU 服务地址
            timeout: 请求超时（秒）
        """
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def parse_pdf(self, file_content: bytes, filename: str = "document.pdf") -> str:
        """
        调用 MinerU HTTP API 将 PDF 转换为 Markdown

        Args:
            file_content: PDF 文件字节内容
            filename: 文件名

        Returns:
            str: Markdown 文本

        Raises:
            RuntimeError: API 调用失败
            TimeoutError: 请求超时
        """
        url = f"{self.api_url}/predict"
        files = {"file": (filename, file_content, "application/pdf")}

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    f"[MinerU] 调用 API: {url}, "
                    f"文件={filename}, 大小={len(file_content)} bytes, "
                    f"尝试={attempt + 1}/{max_retries + 1}"
                )

                start_time = time.time()
                response = self.session.post(
                    url, files=files, timeout=self.timeout
                )
                elapsed = time.time() - start_time

                if response.status_code == 200:
                    result = response.json()
                    markdown_content = self._extract_markdown(result)
                    logger.info(
                        f"[MinerU] 解析成功: {len(markdown_content)} 字符, "
                        f"耗时={elapsed:.1f}s"
                    )
                    return markdown_content
                else:
                    error_msg = f"MinerU API 返回 {response.status_code}: {response.text[:500]}"
                    logger.error(f"[MinerU] {error_msg}")
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    raise RuntimeError(error_msg)

            except requests.exceptions.Timeout:
                logger.warning(f"[MinerU] 请求超时 (timeout={self.timeout}s)")
                if attempt < max_retries:
                    continue
                raise TimeoutError(f"MinerU API 请求超时 ({self.timeout}s)")

            except requests.exceptions.ConnectionError as e:
                logger.error(f"[MinerU] 连接失败: {e}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"无法连接 MinerU 服务: {self.api_url}")

        raise RuntimeError("MinerU API 调用失败：重试次数已用尽")

    def _extract_markdown(self, result: dict) -> str:
        """
        从 MinerU API 响应中提取 Markdown 内容

        支持多种响应格式：
        1. {"markdown_content": "..."}
        2. {"result": {"markdown_content": "..."}}
        3. {"data": {"markdown": "..."}}
        4. 直接返回 markdown 文本
        """
        if isinstance(result, str):
            return result

        # 格式 1: 直接 markdown_content 字段
        if "markdown_content" in result:
            return result["markdown_content"]

        # 格式 2: result 嵌套
        if "result" in result and isinstance(result["result"], dict):
            inner = result["result"]
            if "markdown_content" in inner:
                return inner["markdown_content"]
            if "markdown" in inner:
                return inner["markdown"]

        # 格式 3: data 嵌套
        if "data" in result and isinstance(result["data"], dict):
            inner = result["data"]
            if "markdown" in inner:
                return inner["markdown"]
            if "markdown_content" in inner:
                return inner["markdown_content"]

        # 格式 4: content 字段
        if "content" in result and isinstance(result["content"], str):
            return result["content"]

        # 格式 5: 尝试所有字符串值
        for key, value in result.items():
            if isinstance(value, str) and len(value) > 100:
                logger.warning(f"[MinerU] 未识别的响应格式，尝试使用 '{key}' 字段")
                return value

        raise RuntimeError(f"无法从 MinerU 响应中提取 Markdown: {list(result.keys())}")

    def health_check(self) -> bool:
        """检查 MinerU 服务是否可用"""
        try:
            response = self.session.get(
                f"{self.api_url}/health", timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False


# 单例
_mineru_client: Optional[MinerUClient] = None


def get_mineru_client() -> MinerUClient:
    """获取 MinerU 客户端单例"""
    global _mineru_client
    if _mineru_client is None:
        import sys
        import os
        cur_dir = os.path.dirname(__file__)
        parent_dir = os.path.dirname(cur_dir)
        sys.path.insert(0, parent_dir)
        from config.settings import Settings
        settings = Settings()
        _mineru_client = MinerUClient(
            api_url=settings.mineru_api_url,
            timeout=settings.mineru_timeout,
        )
    return _mineru_client
