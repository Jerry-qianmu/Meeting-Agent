# -*- coding: utf-8 -*-
"""
Query Decompose Node - 通用查询分解
检测复杂查询（对比、多实体、多跳），分解为独立子查询
每个子查询独立检索，合并去重后交给生成阶段

基于 rag-playbook Pattern 05: Query Decomposition
"""

import json
import logging
from datetime import datetime

from ..state import KnowledgeAgentState

logger = logging.getLogger(__name__)

DECOMPOSE_SYSTEM = """你是一个查询分析专家。判断用户问题是否需要分解为多个独立子查询。

## 需要分解的情况
- 对比类：包含"compare/对比/vs/versus/区别/异同"等词，涉及多个实体
- 多实体类：问题中提到 2 个以上独立实体，需要分别查询
- 多跳类：问题需要多步推理，前一步的答案是后一步的输入
- 综合类：问题包含多个独立子问题（"and"/"并且"/"同时"）

## 不需要分解的情况
- 单一实体的简单问题
- 定义类问题（"什么是 X"）
- 操作类问题（"如何做 X"）

## 输出格式
返回 JSON：
{{
  "need_decompose": true/false,
  "reason": "判断原因",
  "sub_queries": ["子查询1", "子查询2", ...]
}}

规则：
- sub_queries 最多 4 个
- 每个子查询必须是独立的、可以直接检索的问题
- 不需要分解时 sub_queries 返回空数组
- **重要**：保持用户原始问题的语言。如果用户用英文提问，子查询必须是英文；如果用中文提问，则用中文。
- 只输出 JSON，不要输出其他内容"""


def query_decompose(state: KnowledgeAgentState) -> dict:
    """Query Decompose Node - 检测复杂查询并分解为子查询"""
    start_time = datetime.now()
    query = state.get("rewritten_query") or state["original_query"]

    # 简单规则预检：包含比较关键词时才调用 LLM
    compare_triggers = [
        "compare", "对比", "比较", "vs", "versus", "区别", "异同",
        "difference", "similar", "不同", "相同", "各自", "分别",
    ]
    multi_entity_triggers = [" and ", " 和 ", " 与 ", " 以及 "]

    query_lower = query.lower()
    likely_complex = any(t in query_lower for t in compare_triggers + multi_entity_triggers)

    if not likely_complex:
        logger.info("[QueryDecompose] 简单查询，跳过分解")
        return {
            "sub_queries": [],
            "processing_log": [{"stage": "query_decompose", "duration_ms": 0, "need_decompose": False}],
        }

    # 调用 LLM 判断
    try:
        from config.settings import Settings
        from service.llm_client import llm_call

        settings = Settings()
        cfg = settings.get_llm_config("rewrite")

        messages = [
            {"role": "system", "content": DECOMPOSE_SYSTEM},
            {"role": "user", "content": f"用户问题：{query}\n\n请分析："},
        ]

        result = llm_call(
            messages=messages, model=cfg["model"], api_type=cfg["api_type"],
            api_key=cfg["api_key"], base_url=cfg["base_url"], temperature=0,
        )

        if result["status_code"] != 200:
            return _no_decompose()

        content = result["content"].strip()
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            return _no_decompose()

        parsed = json.loads(content[json_start:json_end])
        need_decompose = parsed.get("need_decompose", False)
        sub_queries = parsed.get("sub_queries", [])[:4]

        if not need_decompose or len(sub_queries) < 2:
            logger.info(f"[QueryDecompose] 不需要分解")
            return _no_decompose()

        duration = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"[QueryDecompose] 分解为 {len(sub_queries)} 个子查询 ({duration:.0f}ms)")
        for i, sq in enumerate(sub_queries):
            logger.info(f"  [{i+1}] {sq}")

        return {
            "sub_queries": sub_queries,
            "processing_log": [{
                "stage": "query_decompose", "duration_ms": duration,
                "need_decompose": True, "sub_query_count": len(sub_queries),
            }],
        }

    except Exception as e:
        logger.error(f"[QueryDecompose] 异常: {e}")
        return _no_decompose()


def _no_decompose() -> dict:
    return {
        "sub_queries": [],
        "processing_log": [{"stage": "query_decompose", "duration_ms": 0, "need_decompose": False}],
    }
