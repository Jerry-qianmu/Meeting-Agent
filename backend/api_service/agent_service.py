# -*- coding: utf-8 -*-
"""
Knowledge Agent 服务
封装 knowledge_agent 的调用接口
v2: 支持 MCP 工具调用 (web_search)
"""

import asyncio
import logging
import os
import sys
from typing import Dict, Any, Optional, List
from datetime import datetime

# 添加项目路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grand_parent_dir)

from database.mysql.mysql_client import get_db_client
from config.settings import Settings
from service.retrieval_service import get_retrieval_service
from service.embedding_service import get_embedding_service
from api_service.document_service import DocumentService
from api_service.knowledge_base_service import KnowledgeBaseService


logger = logging.getLogger(__name__)


class KnowledgeAgentService:
    """Knowledge Agent 服务类"""

    def __init__(self):
        """初始化 Agent 服务"""
        self.db_client = get_db_client()
        self.retrieval_service = get_retrieval_service()
        self.embedding_service = get_embedding_service()
        self.doc_service = DocumentService(self.db_client)
        self.kb_service = KnowledgeBaseService(self.db_client)

        # Agent 图（延迟初始化）
        self._agent_graph = None

        # MCP 注册表（异步初始化）
        self._mcp_registry = None
        self._mcp_initialized = False

    @property
    def agent_graph(self):
        """懒加载 Agent 图"""
        if self._agent_graph is None:
            try:
                from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
                import pymysql
                from agents.knowledge.graph import create_knowledge_agent_graph

                settings = Settings()
                conn = pymysql.connect(
                    host=settings.mysql_host,
                    port=int(settings.mysql_port),
                    user=settings.mysql_user,
                    password=settings.mysql_password,
                    database=settings.mysql_db,
                    charset="utf8mb4",
                    autocommit=True,
                )
                checkpointer = PyMySQLSaver(conn=conn)
                checkpointer.setup()

                self._agent_graph = create_knowledge_agent_graph(checkpointer)
                logger.info("Knowledge Agent 图初始化成功（PyMySQLSaver checkpointer）")
            except Exception as e:
                logger.error(f"Knowledge Agent 图初始化失败：{e}")
                raise
        return self._agent_graph

    async def _ensure_mcp_initialized(self) -> None:
        """确保 MCP 注册表已初始化"""
        if self._mcp_initialized:
            return

        # 前置检查：npx 是否可用（Windows 上可通过 WSL 桥接）
        import shutil
        import sys
        npx_path = shutil.which("npx") or shutil.which("npx.cmd")
        if not npx_path:
            # Windows 上 npx 可能只在 WSL 里 → 用 wsl 桥接
            if sys.platform == "win32" and shutil.which("wsl"):
                logger.info(
                    "MCP: npx 不在 Windows PATH，将通过 WSL 桥接启动"
                )
            else:
                logger.warning(
                    "MCP 初始化跳过: 找不到 npx，请安装 Node.js (https://nodejs.org) "
                    "并确保 npx 在 PATH 中。"
                )
                self._mcp_initialized = True
                return

        try:
            from service.MCP.mcp_tool_registry import get_mcp_registry
            self._mcp_registry = await get_mcp_registry()
            self._mcp_initialized = True
            logger.info(
                f"MCP 初始化完成: {self._mcp_registry.tool_count} 个工具"
            )
        except Exception as e:
            logger.warning(
                f"MCP 初始化失败（联网搜索将不可用）: {e}",
                exc_info=True
            )
            self._mcp_initialized = True  # 标记已尝试，不再重试

    async def invoke(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        调用 Knowledge Agent 处理查询

        Args:
            query: 用户查询
            config: 可选的配置参数
                - knowledge_base_ids: 指定的知识库 ID 列表
                - document_ids: 指定的文档 ID 列表
                - top_k: 检索结果数量（默认 10）
                - retrieval_strategy: 检索策略
                - web_search_enabled: 是否启用联网搜索（前端开关）
            user_id: 用户 ID
            session_id: 会话 ID

        Returns:
            Dict: Agent 处理结果
        """
        try:
            from langchain_core.messages import HumanMessage

            kb_ids = config.get("knowledge_base_ids", []) if config else []
            doc_ids = config.get("document_ids", []) if config else []
            web_search_enabled = config.get("web_search_enabled", False) if config else False

            # 如果启用了联网搜索，确保 MCP 已初始化
            if web_search_enabled:
                await self._ensure_mcp_initialized()

            initial_state = {
                "messages": [HumanMessage(content=query)],
                "original_query": query,
                "target_knowledge_bases": kb_ids,
                "target_documents": doc_ids,
                "retrieval_strategy": config.get("retrieval_strategy") if config else None,
                "config": self._get_default_config(config),
                "user_id": user_id,
                "session_id": session_id,

                # MCP 工具相关
                "web_search_enabled": web_search_enabled,
                "tool_call_count": 0,
                "max_tool_calls": 5,
            }

            # 调用 Agent（传入 thread_id 用于 checkpointer）
            invoke_config = {}
            if session_id:
                invoke_config = {"configurable": {"thread_id": session_id}}
            # 在独立线程中运行 graph.invoke()，避免阻塞事件循环
            # （MCP 的 _read_loop 需要事件循环来处理响应）
            result = await asyncio.to_thread(
                self.agent_graph.invoke, initial_state, invoke_config
            )

            return self._parse_result(result)

        except Exception as e:
            logger.error(f"Agent 调用失败：{e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }

    def _get_default_config(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取默认配置（从 Settings 读取，确保 .env 生效）"""
        from config.settings import Settings
        s = Settings()

        default_config = {
            # 检索
            "top_k": s.top_k,
            "retrieval_strategy": "hybrid",
            "max_history_turns": s.max_history_turns,
            # rerank
            "rerank_model": s.rerank_model,
            "rerank_limit": s.rerank_limit,
            "rerank_final_top_k": s.rerank_final_top_k,
            # filter
            "light_filter_threshold": s.light_filter_threshold,
            # generation
            "generate_model": s.generation_model,
            "max_context_tokens": s.max_context_tokens,
            # quality
            "quality_eval_model": s.quality_eval_model,
            "quality_max_retries": s.quality_max_retries,
            "quality_score_threshold": s.quality_score_threshold,
            "quality_groundedness_threshold": s.quality_groundedness_threshold,
            "quality_relevance_threshold": s.quality_relevance_threshold,
        }

        logger.info(f"[Config] Settings 读取: top_k={s.top_k}, rerank_limit={s.rerank_limit}, "
                     f"rerank_final_top_k={s.rerank_final_top_k}, max_context_tokens={s.max_context_tokens}, "
                     f"light_filter_threshold={s.light_filter_threshold}")

        if config:
            default_config.update(config)

        return default_config

    def _parse_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """解析 Agent 结果"""
        generation_output = result.get("generation_output", {})
        answer = generation_output.get("answer", "")

        if not answer:
            messages = result.get("messages", [])
            last_message = messages[-1] if messages else None
            if last_message:
                answer = last_message.content if hasattr(last_message, 'content') else str(last_message)

        # context_pack：完整上下文（评估用）
        logger.info(f"[_parse_result] result keys: {list(result.keys())}")
        context_pack = result.get("context_pack", {})
        logger.info(f"[_parse_result] context_pack: {type(context_pack)}, blocks={len(context_pack.get('blocks', [])) if context_pack else 0}")
        context_blocks = context_pack.get("blocks", []) if context_pack else []

        return {
            "success": True,
            "answer": answer,
            "sources": result.get("sources", []),
            "web_search_used": result.get("web_search_used", False),
            "debug": result.get("observability", {}),
            "metadata": {
                "total_duration_ms": result.get("metadata", {}).get("total_duration_ms", 0),
            },
            "follow_up_questions": generation_output.get("follow_up_questions", []),
            "citations": generation_output.get("citations", []),
            # 评估用：完整上下文块（含完整文本、score、doc_id）
            "context_blocks": [
                {
                    "chunk_id": b.get("chunk_id", ""),
                    "doc_id": b.get("doc_id", ""),
                    "text": b.get("text", ""),
                    "score": b.get("score", 0.0),
                }
                for b in context_blocks
            ],
        }


# ── 单例 ──────────────────────────────────────────────────────────────────────

_knowledge_agent_service_instance: Optional[KnowledgeAgentService] = None


def get_knowledge_agent_service() -> KnowledgeAgentService:
    """获取 Knowledge Agent 服务单例"""
    global _knowledge_agent_service_instance
    if _knowledge_agent_service_instance is None:
        _knowledge_agent_service_instance = KnowledgeAgentService()
    return _knowledge_agent_service_instance
