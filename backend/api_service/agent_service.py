# -*- coding: utf-8 -*-
"""
Knowledge Agent 服务
封装 knowledge_agent 的调用接口
"""

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
from service.short_term_memory_service import ShortTermMemoryService
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
        self.memory_service = ShortTermMemoryService(self.db_client)
        self.doc_service = DocumentService(self.db_client)
        self.kb_service = KnowledgeBaseService(self.db_client)
        
        # Agent 图（延迟初始化）
        self._agent_graph = None
        
    @property
    def agent_graph(self):
        """懒加载 Agent 图"""
        if self._agent_graph is None:
            try:
                from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
                import pymysql
                from agents.knowledge.graph import create_knowledge_agent_graph

                # 创建 PyMySQL 连接（独立连接，生命周期与 agent 服务一致）
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
                # 首次运行时自动创建 checkpoint 表
                checkpointer.setup()

                self._agent_graph = create_knowledge_agent_graph(checkpointer)
                logger.info("Knowledge Agent 图初始化成功（PyMySQLSaver checkpointer）")
            except Exception as e:
                logger.error(f"Knowledge Agent 图初始化失败：{e}")
                raise
        return self._agent_graph
    
    async def invoke(self, query: str, config: Optional[Dict[str, Any]] = None, 
                    user_id: Optional[str] = None,
                    session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        调用 Knowledge Agent 处理查询
        
        Args:
            query: 用户查询
            config: 可选的配置参数
                - knowledge_base_ids: 指定的知识库 ID 列表（空列表 = 不使用知识库）
                - document_ids: 指定的文档 ID 列表（空列表 = 不使用文档）
                - top_k: 检索结果数量（默认 10）
                - retrieval_strategy: 检索策略（vector/keyword/hybrid）
            user_id: 用户 ID（用于短期记忆检索）
            session_id: 会话 ID（用于记忆管理，加载历史消息）
        
        Returns:
            Dict: Agent 处理结果
        """
        try:
            # 构建初始状态
            from langchain_core.messages import HumanMessage
            
            # 关键：明确传递 knowledge_base_ids 和 document_ids
            # - 空列表 [] = 用户不想使用知识库/文档，用模型自身知识
            # - 非空列表 = 用户指定了要检索的目标
            kb_ids = config.get("knowledge_base_ids", []) if config else []
            doc_ids = config.get("document_ids", []) if config else []
            
            # 传递 user_id 到 state（用于短期记忆）
            initial_state = {
                "messages": [HumanMessage(content=query)],
                "original_query": query,
                "target_knowledge_bases": kb_ids,  # 明确传递，即使是空列表
                "target_documents": doc_ids,  # 明确传递，即使是空列表
                "retrieval_strategy": config.get("retrieval_strategy") if config else None,
                "config": self._get_default_config(config),
                "user_id": user_id,  # 用于短期记忆
                "session_id": session_id,  # 用于记忆管理（加载历史消息）
            }
            
            # 调用 Agent（传入 thread_id 用于 checkpointer 持久化）
            invoke_config = {}
            if session_id:
                invoke_config = {"configurable": {"thread_id": session_id}}
            result = self.agent_graph.invoke(initial_state, config=invoke_config)
            
            # 解析结果
            return self._parse_result(result)
            
        except Exception as e:
            logger.error(f"Agent 调用失败：{e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }
    
    def _get_default_config(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取默认配置"""
        default_config = {
            "top_k": 10,
            "max_history_turns": 5,
            "retrieval_strategy": "hybrid",
        }
        
        if config:
            default_config.update(config)
        
        return default_config
    
    def _parse_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """解析 Agent 结果"""
        # 答案在 generation_output 字段，不在 messages
        generation_output = result.get("generation_output", {})
        answer = generation_output.get("answer", "")
        
        # 如果没有答案，检查是否是 fallback
        if not answer:
            messages = result.get("messages", [])
            last_message = messages[-1] if messages else None
            if last_message:
                answer = last_message.content if hasattr(last_message, 'content') else str(last_message)
        
        return {
            "success": True,
            "answer": answer,
            "sources": result.get("sources", []),
            "debug": result.get("observability", {}),
            "metadata": {
                "total_duration_ms": result.get("metadata", {}).get("total_duration_ms", 0),
            },
            "follow_up_questions": generation_output.get("follow_up_questions", []),
            "citations": generation_output.get("citations", []),
        }


# ==================== 单例模式 ====================

_knowledge_agent_service_instance: Optional[KnowledgeAgentService] = None


def get_knowledge_agent_service() -> KnowledgeAgentService:
    """
    获取 Knowledge Agent 服务单例
    
    Returns:
        KnowledgeAgentService 实例
    """
    global _knowledge_agent_service_instance
    if _knowledge_agent_service_instance is None:
        _knowledge_agent_service_instance = KnowledgeAgentService()
    return _knowledge_agent_service_instance
