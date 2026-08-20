# -*- coding: utf-8 -*-

import logging
from langgraph.graph import StateGraph, START, END
from typing import Literal, Optional
from langchain_core.messages import AIMessage, ToolMessage

from .state import KnowledgeAgentState
from .node.query_rewrite import query_rewrite
from .node.query_expansion import query_expansion
from .node.query_decompose import query_decompose
from .node.memory_manager import memory_manager
from .node.memory_scribe_node import memory_scribe
from .node.memory_retrieval_node import memory_retrieval
from .node.target_knowledge_or_file import target_knowledge_base, target_documents
from .node.determine_retrieval_strategy import determine_retrieval_strategy
from .node.doc_retrieval import doc_retrieval
from .node.light_filter import light_filter
from .node.rerank import rerank
from .node.chunk_merge import chunk_merge
from .node.chunk_rerank_2 import chunk_rerank_2
from .node.generate_answer import generate_answer
from .node.execute_tool import execute_tool
from .node.check_quality import check_quality
from .node.retrieve_quality_hit import retrieve_quality_hit


# ── Conditional Edge: Quality Retry ───────────────────────────────────────────

def should_retry_retrieval(state: KnowledgeAgentState) -> Literal["retry_retrieval", "return_answer"]:
    """条件边函数：判断是否需要重试检索"""
    retrieval_retry = state.get("retrieval_retry", {})
    quality_decision = state.get("quality_decision", {})

    should_retry = retrieval_retry.get("should_retry", False)
    passed = quality_decision.get("passed", False)
    fallback_used = quality_decision.get("fallback_used", False)

    if passed and not fallback_used:
        return "return_answer"
    if fallback_used:
        return "return_answer"
    if should_retry:
        retry_count = retrieval_retry.get("retry_count", 0)
        max_retries = retrieval_retry.get("max_retries", 2)
        if retry_count < max_retries:
            return "retry_retrieval"

    return "return_answer"


# ── Conditional Edge: MCP Tool Calling ───────────────────────────────────────

def should_call_tool(state: KnowledgeAgentState) -> Literal["call_tool", "continue"]:
    """
    条件边函数：判断是否需要调用 MCP 工具（ReAct 循环）

    检测逻辑：
    1. 最近的消息中是否有 AIMessage 带 tool_calls 待执行
    2. tool_call_count 未达到上限
    3. 如果有 ToolMessage 但后面已有 AIMessage 回应，说明工具已完成
    """
    messages = state.get("messages", [])
    if not messages:
        return "continue"

    tool_call_count = state.get("tool_call_count", 0)
    max_tool_calls = state.get("max_tool_calls", 5)

    # 从后往前扫描消息
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]

        # 找到 AIMessage(tool_calls) — 但需要确认后面没有 ToolMessage
        if isinstance(msg, AIMessage) and msg.tool_calls:
            # 检查这个 AIMessage 之后是否已经有对应的 ToolMessage
            has_response = False
            for j in range(i + 1, len(messages)):
                if isinstance(messages[j], ToolMessage):
                    has_response = True
                    break
                if isinstance(messages[j], AIMessage) and not messages[j].tool_calls:
                    # 已有最终回答，无需再调用
                    return "continue"

            if not has_response and tool_call_count < max_tool_calls:
                logger.info(
                    f"[Graph] should_call_tool → call_tool "
                    f"(count={tool_call_count}/{max_tool_calls})"
                )
                return "call_tool"

        # 如果遇到 HumanMessage 说明这是新一轮对话
        from langchain_core.messages import HumanMessage
        if isinstance(msg, HumanMessage):
            break

    return "continue"


# ── Graph Construction ────────────────────────────────────────────────────────

def create_knowledge_agent_graph(checkpointer) -> StateGraph:
    """
    创建 Knowledge Agent 图

    Args:
        checkpointer: 检查点存储器（PyMySQLSaver），由调用方传入
    """
    knowledge_agent_graph = StateGraph(KnowledgeAgentState)

    # ── 节点注册 ──────────────────────────────────────────────────────────

    # 记忆管理
    knowledge_agent_graph.add_node("memory_manager", memory_manager)
    knowledge_agent_graph.add_node("memory_scribe", memory_scribe)
    knowledge_agent_graph.add_node("memory_retrieval", memory_retrieval)

    # 查询处理
    knowledge_agent_graph.add_node("query_rewrite", query_rewrite)
    knowledge_agent_graph.add_node("query_expansion", query_expansion)
    knowledge_agent_graph.add_node("query_decompose", query_decompose)
    knowledge_agent_graph.add_node("target_knowledege_base", target_knowledge_base)
    knowledge_agent_graph.add_node("target_document", target_documents)
    knowledge_agent_graph.add_node("determine_retrieval_strategy", determine_retrieval_strategy)

    # chunk 处理
    knowledge_agent_graph.add_node("retrieve_chunks", doc_retrieval)
    knowledge_agent_graph.add_node("filter_chunks", light_filter)
    knowledge_agent_graph.add_node("chunk_rerank", rerank)
    knowledge_agent_graph.add_node("chunk_merge", chunk_merge)
    knowledge_agent_graph.add_node("chunk_rerank_2", chunk_rerank_2)

    # 答案生成 + MCP 工具执行（ReAct 循环）
    knowledge_agent_graph.add_node("generate_answer", generate_answer)
    knowledge_agent_graph.add_node("execute_tool", execute_tool)

    # 质量评估与重试
    knowledge_agent_graph.add_node("check_quality", check_quality)
    knowledge_agent_graph.add_node("retrieve_quality_hit", retrieve_quality_hit)

    # ── 边 ────────────────────────────────────────────────────────────────

    # 启动 → 记忆管理 → 碎片提取 → 查询重写
    knowledge_agent_graph.add_edge(START, "memory_manager")
    knowledge_agent_graph.add_edge("memory_manager", "memory_scribe")
    knowledge_agent_graph.add_edge("memory_scribe", "query_rewrite")

    # 查询处理阶段
    knowledge_agent_graph.add_edge("query_rewrite", "query_expansion")
    knowledge_agent_graph.add_edge("query_expansion", "query_decompose")
    knowledge_agent_graph.add_edge("query_decompose", "target_knowledege_base")
    knowledge_agent_graph.add_edge("target_knowledege_base", "target_document")
    knowledge_agent_graph.add_edge("target_document", "determine_retrieval_strategy")

    # 检索处理阶段
    knowledge_agent_graph.add_edge("determine_retrieval_strategy", "retrieve_chunks")
    knowledge_agent_graph.add_edge("retrieve_chunks", "filter_chunks")
    knowledge_agent_graph.add_edge("filter_chunks", "chunk_rerank")
    knowledge_agent_graph.add_edge("chunk_rerank", "chunk_merge")
    knowledge_agent_graph.add_edge("chunk_merge", "chunk_rerank_2")

    # 记忆检索 → 生成答案 → 条件边：MCP tool-calling 或 质量评估
    knowledge_agent_graph.add_edge("chunk_rerank_2", "memory_retrieval")
    knowledge_agent_graph.add_edge("memory_retrieval", "generate_answer")

    knowledge_agent_graph.add_conditional_edges(
        "generate_answer",
        should_call_tool,
        {
            "call_tool": "execute_tool",    # ReAct: 执行工具
            "continue": "check_quality",    # 正常流程: 质量评估
        },
    )

    # execute_tool → 回到 generate_answer（ReAct 循环）
    knowledge_agent_graph.add_edge("execute_tool", "generate_answer")

    # 质量评估阶段
    knowledge_agent_graph.add_edge("check_quality", "retrieve_quality_hit")

    # 条件边：质量驱动的检索重试
    knowledge_agent_graph.add_conditional_edges(
        "retrieve_quality_hit",
        should_retry_retrieval,
        {
            "retry_retrieval": "retrieve_chunks",
            "return_answer": END,
        },
    )

    graph = knowledge_agent_graph.compile(checkpointer=checkpointer)
    return graph
