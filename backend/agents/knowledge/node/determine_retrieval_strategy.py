# -*- coding: utf-8 -*-
"""
Enterprise Knowledge Base QA Agent State Definition
Complete state management for production RAG system
"""

from typing_extensions import TypedDict
from typing import List, Dict, Any, Optional, Annotated
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import operator

# LangGraph 消息处理
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage

import logging
logger = logging.getLogger(__name__)

# 也预留一个前端接口选择
from pydantic import BaseModel
from typing import Literal
from dashscope import Generation
import os, sys

cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.append(os.path.dirname(grand_parent_dir))

from config.settings import Settings
settings = Settings()
from ..state import KnowledgeAgentState

VECTOR_ONLY = "vector_only"
KEYWORD_ONLY = "keyword_only"
HYBRID = "hybrid"

class StrategyOutput(BaseModel):
    strategy: Literal["vector_only", "keyword_only", "hybrid"]
    reason: str

import json

def call_llm_decide_strategy(query: str,model:str) -> str:
    from ..prompt.retrieval_strategy import DETERMINE_RETRIEVAL_STRATEGY
    from service.llm_client import llm_call
    prompt = DETERMINE_RETRIEVAL_STRATEGY.format(query=query)
    cfg = settings.get_llm_config("rewrite", model=model)
    result = llm_call(
        messages=[{"role": "user", "content": prompt}],
        model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"], base_url=cfg["base_url"],
        temperature=0,
    )

    if result["status_code"] != 200:
        return {"strategy": HYBRID, "reason": "llm_error"}

    text = result["content"].strip()

    try:
        data = json.loads(text)
        parsed = StrategyOutput(**data)
        return {
            "strategy": parsed.strategy,
            "reason": parsed.reason
        }
    except Exception:
        return {"strategy": HYBRID, "reason": "parse_error"}

def determine_retrieval_strategy(state: KnowledgeAgentState) -> dict:
    start_time = datetime.now()
    try:
        query = state["rewritten_query"]
        retrieval_strategy = state.get('retrieval_strategy')
        config = state.get("config", {})
        
        # 如果从 config 中获取模型
        if isinstance(config, dict):
            llm_model = config.get("determine_retrieval_strategy_model", settings.determine_retrieval_strategy_model)
        else:
            # 如果是 RAGconfig 对象
            llm_model = getattr(config, "determine_retrieval_strategy_model", settings.determine_retrieval_strategy_model)

        # 从前端接收检索方式，在这次对话初始的时候传入
        if retrieval_strategy:
            logger.info("Retrieval Strategy: %s", retrieval_strategy)

            return {
                "retrieval_strategy": retrieval_strategy,
                "processing_log": [{"stage": "retrieval_strategy", "duration_ms": 0, "strategy": retrieval_strategy}]
            }
        else:# 如果前端没有选择检索方式，则调用 LLM 进行判断
            result = call_llm_decide_strategy(query, llm_model)

            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            return {
            "retrieval_strategy": result["strategy"],
            "retrieval_strategy_reason": result["reason"],
            "processing_log": [{
                "stage": "retrieval_strategy",
                "duration_ms": duration,
                "retrieval_strategy": result["strategy"],
                "retrieval_strategy_reason": result["reason"]
            }]
        }

    except Exception as e:
        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        return {
            "retrieval_strategy": HYBRID,
            "processing_log": [{
                "stage": "retrieval_strategy",
                "duration_ms": duration,
                "error": str(e),
            }]
        }