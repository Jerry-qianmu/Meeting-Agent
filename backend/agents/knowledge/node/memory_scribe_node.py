# -*- coding: utf-8 -*-
"""
Memory Scribe Node - 记忆碎片提取节点

在 memory_manager 之后运行，从上一轮对话中增量提取记忆碎片
"""

import logging
from typing import Dict, Any

from config.settings import Settings

logger = logging.getLogger(__name__)
from service.memory.config import MemoryConfig
settings = Settings()

# Milvus 单例（避免重复连接）
_milvus_instance = None
def _get_milvus():
    global _milvus_instance
    if _milvus_instance is None:
        try:
            from database.milvus.milvus_service import MilvusService
            _milvus_instance = MilvusService()
        except Exception:
            pass
    return _milvus_instance

# 最少消息数才触发提取（4条 = 至少2轮对话）
SCRIBE_MIN_MESSAGES = 4


def memory_scribe(state: Dict[str, Any]) -> dict:
    """Memory Scribe Node - 从历史消息中增量提取记忆碎片"""
    session_id = state.get("session_id")
    user_id = state.get("user_id")

    if not session_id or not user_id:
        logger.info("[MemoryScribe] 跳过: 无 session_id 或 user_id")
        return {}

    history_messages = state.get("history_messages", [])

    if not history_messages or len(history_messages) < SCRIBE_MIN_MESSAGES:
        logger.info(
            f"[MemoryScribe] 跳过: 历史消息 {len(history_messages)} 条, 需要 ≥{SCRIBE_MIN_MESSAGES}"
        )
        return {}

    try:
        from service.memory.scribe import InterviewScribe
        from database.mysql.mysql_client import get_db_client

        db_client = get_db_client()
        if not db_client:
            logger.warning("[MemoryScribe] DB 客户端未初始化")
            return {}

        recent_messages = history_messages[-20:]
        messages_dict = []
        for msg in recent_messages:
            if hasattr(msg, 'content'):
                role = 0 if msg.type == 'human' else 1 if msg.type == 'ai' else 2
                messages_dict.append({'role': role, 'content': msg.content or ''})

        logger.info(f"[MemoryScribe] 准备提取: {len(messages_dict)} 条消息, session={session_id[:8]}...")

        # 获取 embedding 和 milvus 服务（可选，用于向量索引）
        embedding_service = None
        try:
            from service.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
        except Exception:
            pass
        milvus_service = _get_milvus()

        scribe = InterviewScribe(
            db_client=db_client,
            api_key=MemoryConfig.DASHSCOPE_API_KEY,
            embedding_service=embedding_service,
            milvus_service=milvus_service,
        )

        fragments = scribe.extract_incremental(session_id, user_id, messages_dict)
        if fragments:
            logger.info(f"[MemoryScribe] 提取 {len(fragments)} 条碎片")
        else:
            logger.info("[MemoryScribe] LLM 未提取到碎片")

        return {}

    except Exception as e:
        logger.error(f"[MemoryScribe] 提取失败: {e}", exc_info=True)
        return {}
