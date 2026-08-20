# -*- coding: utf-8 -*-
"""
统一的 Token 计数工具
使用 tiktoken 的 cl100k_base 编码（与 OpenAI embedding 模型兼容，对中文友好）
"""

import logging

logger = logging.getLogger(__name__)

_encoder = None


def _get_encoder():
    """延迟加载 tiktoken encoder（单例）"""
    global _encoder
    if _encoder is None:
        try:
            import tiktoken
            _encoder = tiktoken.get_encoding("cl100k_base")
            logger.info("[Tokenizer] tiktoken cl100k_base 加载成功")
        except ImportError:
            logger.warning("[Tokenizer] tiktoken 未安装，降级为启发式估算")
            _encoder = "fallback"
    return _encoder


def count_tokens(text: str) -> int:
    """
    计算文本的 token 数

    Args:
        text: 输入文本

    Returns:
        int: token 数量
    """
    if not text:
        return 0

    encoder = _get_encoder()

    if encoder == "fallback":
        return _estimate_tokens_heuristic(text)

    try:
        return len(encoder.encode(text))
    except Exception as e:
        logger.warning(f"[Tokenizer] tiktoken 编码失败，降级为启发式: {e}")
        return _estimate_tokens_heuristic(text)


def _estimate_tokens_heuristic(text: str) -> int:
    """启发式估算（tiktoken 不可用时的降级方案）"""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - chinese_chars
    return max(1, int(chinese_chars * 1.5 + other_chars * 0.3))
