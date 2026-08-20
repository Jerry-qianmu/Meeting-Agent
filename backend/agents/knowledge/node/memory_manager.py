# -*- coding: utf-8 -*-
"""
Memory Manager Node - 短期记忆管理
职责：
1. 从缓存或 DB 加载当前 session 的历史消息
2. 计算 token 总量，判断是否需要压缩
3. 压缩旧消息为 history_prompt（摘要记忆）
4. 保留近 N 轮作为缓冲区（history_messages）
5. 不修改 messages（messages 只放当前轮）

缓存策略：
- 模块级 _session_cache 按 session_id 缓存
- graph 启动时先读缓存，miss 时读 DB
- controller 保存新消息后调用 append_to_cache() 更新
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from service.tokenizer import count_tokens
from config.settings import Settings
from ..state import KnowledgeAgentState
from ..prompt.memory_prompt import MEMORY_COMPRESS_SYSTEM

logger = logging.getLogger(__name__)
settings = Settings()


# ============================================================
# 模块级缓存：按 session_id 缓存历史消息
# ============================================================
_session_cache: Dict[str, Dict[str, Any]] = {}


def get_cache(session_id: str) -> Optional[Dict[str, Any]]:
    """获取 session 缓存"""
    return _session_cache.get(session_id)


def update_cache(session_id: str, db_messages: List[Dict[str, Any]]):
    """
    更新缓存（controller 保存新消息后调用）
    将整个 session 的 DB 消息写入缓存
    """
    _session_cache[session_id] = {
        "db_messages": db_messages,
        "updated_at": datetime.now(),
    }
    logger.info(f"[MemoryCache] 缓存已更新: session={session_id}, 消息数={len(db_messages)}")


def append_to_cache(session_id: str, new_messages: List[Dict[str, Any]]):
    """
    追加消息到缓存（controller 保存后调用）
    如果缓存不存在则忽略（下次 graph 运行时会从 DB 加载）
    """
    cache = _session_cache.get(session_id)
    if cache:
        cache["db_messages"].extend(new_messages)
        cache["updated_at"] = datetime.now()
        logger.info(f"[MemoryCache] 缓存追加: session={session_id}, 新增={len(new_messages)}条")
    else:
        logger.debug(f"[MemoryCache] 缓存不存在，跳过追加: session={session_id}")


def clear_cache(session_id: str):
    """清除指定 session 的缓存"""
    _session_cache.pop(session_id, None)


def clear_all_cache():
    """清除所有缓存"""
    _session_cache.clear()


# ============================================================
# 工具函数
# ============================================================

def count_tokens(text: str) -> int:
    """粗略估算 token 数：中文约 1.5 token/字，英文约 1 token/词"""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars * 0.4)


def _format_history_for_compress(messages: List[Dict[str, Any]]) -> str:
    """将历史消息格式化为压缩 prompt 的输入"""
    lines = []
    for msg in messages:
        role_int = msg.get("role", 0)
        role = "用户" if role_int == 0 else "助手"
        content = msg.get("content", "") or ""
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"{role}：{content}")
    return "\n".join(lines)


def _compress_history(history_text: str, model: str) -> str:
    """调用 LLM 压缩历史对话"""
    messages = [
        {"role": "system", "content": MEMORY_COMPRESS_SYSTEM},
        {"role": "user", "content": f"请压缩以下对话历史：\n\n{history_text}"}
    ]

    try:
        from service.llm_client import llm_call
        cfg = settings.get_llm_config("memory_compress", model=model)
        result = llm_call(messages=messages, model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"], base_url=cfg["base_url"])
        if result["status_code"] == 200:
            compressed = (result["content"] or "").strip()
            return compressed
        else:
            logger.warning(f"[MemoryManager] 压缩 API 错误: {response.status_code} {response.message}")
            return ""
    except Exception as e:
        logger.error(f"[MemoryManager] 压缩失败: {e}", exc_info=True)
        return ""


def _db_messages_to_lc(db_messages: List[Dict[str, Any]]) -> List[BaseMessage]:
    """将 DB 消息转换为 LangChain 消息对象"""
    lc_messages = []
    for msg in db_messages:
        role = msg.get("role", 0)
        content = msg.get("content", "") or ""
        if role == 0:  # user
            lc_messages.append(HumanMessage(content=content))
        elif role == 1:  # assistant
            lc_messages.append(AIMessage(content=content))
    return lc_messages


def _load_db_messages(session_id: str) -> List[Dict[str, Any]]:
    """从 DB 加载 session 的全部历史消息"""
    from database.mysql.mysql_client import get_db_client
    from database.mysql.repository.message_repository import MessageRepository

    db_client = get_db_client()
    message_repo = MessageRepository(db_client)
    return message_repo.get_session_messages(session_id, limit=500)


# ============================================================
# 核心节点
# ============================================================

def memory_manager(state: KnowledgeAgentState) -> dict:
    """
    Memory Manager Node

    流程：
    1. 无 session_id → 跳过
    2. checkpoint 感知：如果 history_messages 已有数据（从 checkpoint 恢复），跳过加载
    3. 优先读缓存，miss 时从 DB 加载
    4. 计算 token 总量
    5. 超阈值 → 压缩旧消息为 history_prompt，保留近 N 轮到 history_messages
    6. 未超阈值 → 全部放入 history_messages，history_prompt 为空

    注意：不修改 messages，messages 只放当前轮
    """
    start_time = datetime.now()
    session_id = state.get("session_id")

    if not session_id:
        logger.info("[MemoryManager] 无 session_id，跳过记忆管理")
        return {}

    try:
        # ── 1. 加载历史消息（优先缓存） ──
        cache = get_cache(session_id)
        if cache:
            db_messages = cache["db_messages"]
            logger.info(f"[MemoryManager] 命中缓存: session={session_id}, 消息数={len(db_messages)}")
        else:
            db_messages = _load_db_messages(session_id)
            update_cache(session_id, db_messages)
            logger.info(f"[MemoryManager] 从 DB 加载: session={session_id}, 消息数={len(db_messages)}")

        if not db_messages:
            logger.info(f"[MemoryManager] session {session_id} 无历史消息")
            return {"history_prompt": "", "history_messages": []}

        # ── 2. 计算 token 总量 ──
        total_tokens = 0
        for msg in db_messages:
            content = msg.get("content", "") or ""
            total_tokens += count_tokens(content)

        logger.info(
            f"[MemoryManager] session={session_id}, "
            f"历史消息={len(db_messages)}条, 估算token={total_tokens}, "
            f"阈值={settings.memory_token_threshold}"
        )

        # ── 3. 按阈值分流 ──
        buffer_rounds = settings.memory_buffer_rounds
        buffer_msg_count = buffer_rounds * 2  # 每轮 = 1 user + 1 assistant

        if total_tokens <= settings.memory_token_threshold:
            # 未超阈值：全部作为缓冲区
            logger.info("[MemoryManager] token 未超阈值，全部作为缓冲区")
            buffer_lc = _db_messages_to_lc(db_messages)
            return {
                "history_messages": buffer_lc,
                "history_prompt": "",
            }
        else:
            # 超过阈值：压缩旧消息，保留最近 N 轮
            logger.info(f"[MemoryManager] token 超阈值，压缩旧消息，保留最近 {buffer_rounds} 轮")

            if len(db_messages) > buffer_msg_count:
                old_messages = db_messages[:-buffer_msg_count]
                recent_messages = db_messages[-buffer_msg_count:]
            else:
                old_messages = []
                recent_messages = db_messages

            # 压缩旧消息
            history_prompt = ""
            if old_messages:
                history_text = _format_history_for_compress(old_messages)
                compress_model = settings.memory_compress_model
                history_prompt = _compress_history(history_text, compress_model)
                if not history_prompt:
                    # 压缩失败降级
                    fallback_msgs = old_messages[-6:]
                    fallback_lines = []
                    for msg in fallback_msgs:
                        role = "用户" if msg.get("role") == 0 else "助手"
                        fallback_lines.append(f"{role}：{msg.get('content', '')[:200]}")
                    history_prompt = "（历史摘要-降级模式）\n" + "\n".join(fallback_lines)

            buffer_lc = _db_messages_to_lc(recent_messages)

            duration = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(
                f"[MemoryManager] 完成 ({duration:.0f}ms): "
                f"压缩={len(old_messages)}条, 缓冲区={len(recent_messages)}条, "
                f"history_prompt={len(history_prompt)}字"
            )

            return {
                "history_messages": buffer_lc,
                "history_prompt": history_prompt,
            }

    except Exception as e:
        logger.error(f"[MemoryManager] 记忆管理失败: {e}", exc_info=True)
        return {"history_prompt": "", "history_messages": []}
