# -*- coding: utf-8 -*-
"""
knowledge_agent.state
"""

from typing_extensions import TypedDict
from typing import List, Dict, Any, Optional, Annotated
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import operator

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

# 导入 structure_info 模块
from .structure_info.RAGconfig import RAGconfig
from .structure_info.processing_log import ProcessingLogItem
from .structure_info.chunk import Chunk, Chunk_Filter_Decision, Chunk_Filter_Stats
from .structure_info.context import ContextPack, GenerationOutput
from .structure_info.quality import QualityDecision, RetrievalRetryState
from .structure_info.Debug import Observability


class KnowledgeAgentState(TypedDict, total=False):
    """
    State strictly aligned with:
    query_rewrite → query_expansion → routing → retrieval → filtering → rerank → diversity → compression → build → generate → quality
    """
    # =========================================================
    # 0. 检索过程中模型相关参数配置
    # =========================================================
    config: RAGconfig

    # =========================================================
    # 1. Conversation Memory
    # =========================================================
    session_id: Optional[str]                           # 当前会话 ID（前端传入）
    messages: Annotated[List[BaseMessage], add_messages] # 当前轮消息（自动追加）
    history_messages: List[BaseMessage]                  # 历史缓冲区（最近 N 轮，由 memory_manager 填充）
    history_prompt: Optional[str]                       # 压缩后的历史记忆摘要


    # =========================================================
    # 2. Query Layer (query_rewrite + expansion)
    # =========================================================
    original_query: str
    rewritten_query: Optional[str]
    processing_log: Annotated[List[ProcessingLogItem], operator.add]


    """待完成"""
    # Query Expansion
    # expanded_queries: List[str]
    # query_intent: Optional[str]         # factual / procedural / comparative
    # query_keywords: List[str]
    # query_entities: List[Dict[str, Any]]


    # =========================================================
    # 3. Routing Layer (target_kb + target_docs + strategy)
    # =========================================================
    target_knowledge_bases: List[str]
    target_documents: List[str]

    retrieval_strategy: Optional[str]   # vector / keyword / hybrid
    retrieval_strategy_reason: Optional[str] #用一个带 prompt 的 llm 进行决策，检索方式，并给出原因


    # =========================================================
    # 4. Retrieval Layer
    # =========================================================
    retrieval_results: Dict[str, List[Chunk]]
    merged_chunks: List[Chunk]
    retrieval_params: Dict[str, Any]


    # =========================================================
    # 5. Light_Filtering Layer
    # =========================================================
    Light_filtered_chunks: List[Chunk]
    filter_stats: Chunk_Filter_Stats


    # =========================================================
    # 6. Rerank Layer
    # =========================================================
    reranked_chunks: List[Chunk]

    # =========================================================
    # 7. Diversity Selection Layer(暂时不要)
    # =========================================================

    # selection_results: List[ChunkSelectionResult]
    # selected_chunks: List[Chunk]


    # =========================================================
    # 8. Context Construction Layer
    # =========================================================
    context_pack: ContextPack
    sources: List[Dict[str, Any]]


    # =========================================================
    # 9. Generation Layer
    # =========================================================
    generation_output: GenerationOutput
    sources: List[Dict[str, Any]]


    # =========================================================
    # 10. Quality Control Layer
    # =========================================================
    quality_decision: QualityDecision


    # =========================================================
    # 11. Quality-driven Retrieval Loop
    # =========================================================
    retrieval_retry: RetrievalRetryState

    # =========================================================
    # 12. Observability / Debug
    # =========================================================
    observability: Observability
