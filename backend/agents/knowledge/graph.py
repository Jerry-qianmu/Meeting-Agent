# -*- coding: utf-8 -*-

from langgraph.graph import StateGraph, START, END
from typing import Literal, Optional
from .state import KnowledgeAgentState
from .node.query_rewrite import query_rewrite
from .node.memory_manager import memory_manager
from .node.target_knowledge_or_file import target_knowledge_base, target_documents
from .node.determine_retrieval_strategy import determine_retrieval_strategy
from .node.doc_retrieval import doc_retrieval
from .node.light_filter import light_filter
from .node.rerank import rerank
from .node.generate_answer import generate_answer
from .node.check_quality import check_quality
from .node.retrieve_quality_hit import retrieve_quality_hit


def should_retry_retrieval(state: KnowledgeAgentState) -> Literal["retry_retrieval", "return_answer"]:
    """
    条件边函数：判断是否需要重试检索
    
    返回:
        "retry_retrieval" → 回到 doc_retrieval 重新检索
        "return_answer" → 返回最终答案
    """
    retrieval_retry = state.get("retrieval_retry", {})
    quality_decision = state.get("quality_decision", {})
    
    should_retry = retrieval_retry.get("should_retry", False)
    passed = quality_decision.get("passed", False)
    fallback_used = quality_decision.get("fallback_used", False)
    
    # 质量达标且未使用 fallback → 返回答案
    if passed and not fallback_used:
        return "return_answer"
    
    # 已使用 fallback → 返回答案
    if fallback_used:
        return "return_answer"
    
    # 需要重试且未达最大次数 → 重试
    if should_retry:
        retry_count = retrieval_retry.get("retry_count", 0)
        max_retries = retrieval_retry.get("max_retries", 2)
        if retry_count < max_retries:
            return "retry_retrieval"
    
    # 默认返回答案
    return "return_answer"


def create_knowledge_agent_graph(checkpointer) -> StateGraph:
    """
    创建 Knowledge Agent 图
    
    Args:
        checkpointer: 检查点存储器（MySQLSaver），由调用方传入
    """
    knowledge_agent_graph = StateGraph(KnowledgeAgentState)
   #"""添加节点"""------------------------------------------------------------------------------------------------

    knowledge_agent_graph.add_node("memory_manager", memory_manager)  # 短期记忆管理（加载历史、压缩、缓冲区）
    knowledge_agent_graph.add_node("query_rewrite", query_rewrite)  # rewrite query
    knowledge_agent_graph.add_node("target_knowledege_base", target_knowledge_base)  # 是否指定目标知识库回答
    knowledge_agent_graph.add_node("target_document", target_documents)  # 是否指定目标文档
    knowledge_agent_graph.add_node("determine_retrieval_strategy", determine_retrieval_strategy)  # 确定检索策略
    
    """chunk 处理"""
    knowledge_agent_graph.add_node("retrieve_chunks", doc_retrieval)  # 检索文档 chunk
    knowledge_agent_graph.add_node("filter_chunks", light_filter)  # 过滤低相似，重复 chunk 等
    knowledge_agent_graph.add_node("chunk_rerank", rerank)  # 重新排序 chunk
    
    """context 组装"""
    knowledge_agent_graph.add_node("generate_answer", generate_answer)  # 生成答案
    
    """质量评估与重试"""
    knowledge_agent_graph.add_node("check_quality", check_quality)  # 质量评估
    knowledge_agent_graph.add_node("retrieve_quality_hit", retrieve_quality_hit)  # 质量驱动的重试决策

    #"""添加边"""-------------------------------------------------------------------------------------------------

    # 启动流程
    knowledge_agent_graph.add_edge(START, "memory_manager")
    knowledge_agent_graph.add_edge("memory_manager", "query_rewrite")
    
    # 查询处理阶段
    knowledge_agent_graph.add_edge("query_rewrite", "target_knowledege_base")
    # knowledge_agent_graph.add_edge("query_rewrite", "query_expansion")
    # knowledge_agent_graph.add_edge("query_expansion", "target_knowledege_base")
    
    # 目标选择阶段
    knowledge_agent_graph.add_edge("target_knowledege_base", "target_document")
    knowledge_agent_graph.add_edge("target_document", "determine_retrieval_strategy")
    
    # 检索处理阶段
    knowledge_agent_graph.add_edge("determine_retrieval_strategy", "retrieve_chunks")
    knowledge_agent_graph.add_edge("retrieve_chunks", "filter_chunks")
    knowledge_agent_graph.add_edge("filter_chunks", "chunk_rerank")
    
    # 生成答案阶段
    knowledge_agent_graph.add_edge("chunk_rerank", "generate_answer")
    
    # 质量评估阶段
    knowledge_agent_graph.add_edge("generate_answer", "check_quality")
    knowledge_agent_graph.add_edge("check_quality", "retrieve_quality_hit")
    
    # 条件边：根据质量评估结果决定是否重试
    knowledge_agent_graph.add_conditional_edges(
        "retrieve_quality_hit",
        should_retry_retrieval,
        {
            "retry_retrieval": "retrieve_chunks",  # 重试：回到检索阶段
            "return_answer": END  # 返回答案：结束
        }
    )

    graph = knowledge_agent_graph.compile(checkpointer=checkpointer)

    return graph
