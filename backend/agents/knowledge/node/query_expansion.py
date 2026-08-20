# -*- coding: utf-8 -*-
"""
Query Expansion Node - 多查询扩展
基于改写后的 query 生成多个变体，用于多路检索合并
"""

import json
import logging
from datetime import datetime

from dashscope import Generation
from config.settings import Settings
from ..state import KnowledgeAgentState

logger = logging.getLogger(__name__)
settings = Settings()

EXPANSION_PROMPT = """你是一个搜索查询扩展专家。根据用户的问题，生成 {n} 个不同角度的变体查询，用于检索。

要求：
- 保留原始语义
- 使用不同的措辞和表达方式
- 包含同义词替换、关键术语扩展、意图细分
- 每个查询简洁明了
- 不要重复

原始问题：{query}

输出格式（严格 JSON 数组）：
["变体查询1", "变体查询2", "变体查询3"]

只输出 JSON 数组，不要输出其他内容。"""


def query_expansion(state: KnowledgeAgentState) -> dict:
    """
    Query Expansion Node - 生成多查询变体

    输入：rewritten_query
    输出：expanded_queries（变体列表，包含原始 query）
    """
    start_time = datetime.now()
    query = state.get("rewritten_query") or state["original_query"]
    expansion_count = 3

    try:
        if not settings.llm_api_key:
            return {"expanded_queries": [query]}

        prompt = EXPANSION_PROMPT.format(n=expansion_count, query=query)

        from service.llm_client import llm_call
        cfg = settings.get_llm_config("rewrite")
        result = llm_call(
            messages=[{"role": "user", "content": prompt}],
            model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"], base_url=cfg["base_url"],
        )

        if result["status_code"] != 200:
            logger.warning(f"[QueryExpansion] LLM 调用失败: {result['status_code']}")
            return {"expanded_queries": [query]}

        content = result["content"]

        start = content.find("[")
        end = content.rfind("]") + 1
        if start >= 0 and end > start:
            variants = json.loads(content[start:end])
            variants = [v.strip() for v in variants if v.strip() and v.strip() != query]
            expanded = [query] + variants[:expansion_count]
        else:
            logger.warning(f"[QueryExpansion] JSON 解析失败: {content[:200]}")
            expanded = [query]

    except Exception as e:
        logger.error(f"[QueryExpansion] 异常: {e}")
        expanded = [query]

    duration = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(f"[QueryExpansion] 生成 {len(expanded)} 个查询 ({duration:.0f}ms)")

    return {
        "expanded_queries": expanded,
        "processing_log": [{
            "stage": "query_expansion",
            "duration_ms": duration,
            "query_count": len(expanded),
        }],
    }
