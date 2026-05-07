"""
Query Rewrite Node - 增强改写用户提问，支持多轮对话指代消解
"""

import logging
from datetime import datetime

from dashscope import Generation
import os
import sys

logger = logging.getLogger(__name__)
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.append(os.path.dirname(grand_parent_dir))

from config.settings import Settings
settings = Settings()
print(settings.dashscope_api_key)

from ..state import KnowledgeAgentState
from ..prompt.query_write_prompt import KNOWLEDGE_QUERY_REWRITE_WITH_HISTORY_SYSTEM, KNOWLEDGE_QUERY_REWRITE_SYSTEM


# 带入历史的最大轮数（太长会干扰改写，取最近 3 轮即可）
_MAX_HISTORY_TURNS = settings.max_history_turns

def query_rewrite(state: KnowledgeAgentState) -> dict:
    """
    Query Rewrite Node - 提问改写
    支持压缩历史（history_prompt）+ 缓冲区（history_messages）两层记忆
    """
    logging.info("Query Rewrite Node - 提问改写")
    start_time = datetime.now()

    try:
        original_query = state["original_query"]
        history_prompt = state.get("history_prompt", "") or ""

        # 从 history_messages 读缓冲区（memory_manager 已加载，不含当前轮）
        history_messages = state.get("history_messages", [])
        # 取最近 N 轮
        recent_history = history_messages[-(2 * _MAX_HISTORY_TURNS):]

        # 构建历史上下文部分（压缩摘要 + 近期对话）
        history_context_parts = []
        if history_prompt:
            history_context_parts.append(f"【历史对话摘要】\n{history_prompt}")
        if recent_history:
            recent_lines = []
            for msg in recent_history:
                if hasattr(msg, "type"):
                    if msg.type == "human":
                        recent_lines.append(f"用户：{msg.content}")
                    elif msg.type == "ai":
                        recent_lines.append(f"助手：{msg.content or ''}")
            if recent_lines:
                history_context_parts.append("【近期对话】\n" + "\n".join(recent_lines))

        if history_context_parts:
            system_prompt = KNOWLEDGE_QUERY_REWRITE_WITH_HISTORY_SYSTEM
            full_history = "\n\n".join(history_context_parts)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"对话历史：\n{full_history}\n\n当前问题：{original_query}\n\n改写后的问题："}
            ]
            logger.info(f"[QueryRewrite] 带历史改写（压缩={bool(history_prompt)}, 缓冲区={len(recent_history)}条）: {original_query}")
        else:
            # 无历史：用简单版 prompt
            system_prompt = KNOWLEDGE_QUERY_REWRITE_SYSTEM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"原始问题: {original_query}\n\n改写后的问题:"},
            ]
            logger.info(f"[QueryRewrite] 无历史改写：{original_query}")

        # 检查 API Key 是否有效
        if not settings.dashscope_api_key:
            logger.warning("[QueryRewrite] DashScope API Key 未设置，使用原始 query")
            rewritten_query = original_query
        else:
            response = Generation.call(
                api_key=settings.dashscope_api_key,
                model=state["config"].get("rewrite_model", settings.rewrite_model),
                messages=messages,
                result_format="message",
            )
            if response.status_code == 200:
                try:
                    rewritten_query = (
                        response.output.choices[0].message.get("content") or ""
                    ).strip()
                except (KeyError, IndexError, AttributeError):
                    rewritten_query = ""
            else:
                logger.warning(
                    f"[QueryRewrite] DashScope error {response.status_code}: {response.message}, 使用原始 query"
                )
                rewritten_query = ""

        if not rewritten_query or len(rewritten_query) < 2:
            rewritten_query = original_query

        duration = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"[QueryRewrite] 完成 ({duration:.0f}ms): {original_query} → {rewritten_query}")

        #from ..structure_info.processing_log import query_rewrite_output
        return {
            "rewritten_query": rewritten_query,
            "processing_log": [
                {
                    "stage": "query_rewrite",
                    "duration_ms": duration,
                    "original": original_query,
                    "rewritten": rewritten_query,
                    "history_turns": len(recent_history) // 2,
                }
            ]
        }

    except Exception as e:
        logger.error(f"[QueryRewrite] 改写失败: {e}", exc_info=True)
        return {
            "original_query": state["original_query"],
            "rewritten_query": state["original_query"],
            "processing_log": [f"问题改写失败，使用原始问题: {e}"],
        }

