# -*- coding: utf-8 -*-
"""
Agent API 控制器
提供 Knowledge Agent 的聊天接口
"""

import logging
import os
import sys
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grand_parent_dir)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["Agent"])


# ── Request/Response Models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """聊天请求"""
    session_id: str = Field(..., description="会话 ID")
    query: str = Field(..., description="用户查询", min_length=1, max_length=4000)
    knowledge_base_ids: Optional[List[str]] = Field(None, description="指定的知识库 ID 列表")
    document_ids: Optional[List[str]] = Field(None, description="指定的文档 ID 列表")
    top_k: Optional[int] = Field(None, description="检索结果数量（不传则用 .env 中的 TOP_K）", ge=1, le=50)
    retrieval_strategy: Optional[str] = Field(None, description="检索策略：vector/keyword/hybrid")
    stream: Optional[bool] = Field(False, description="是否流式响应")
    web_search_enabled: Optional[bool] = Field(False, description="是否启用联网搜索")


class ChatResponse(BaseModel):
    """聊天响应"""
    success: bool
    answer: str
    sources: Optional[List[Dict[str, Any]]] = None
    debug: Optional[Dict[str, Any]] = None
    context_blocks: Optional[List[Dict[str, Any]]] = None  # 评估用：完整上下文


class AgentStatusResponse(BaseModel):
    """Agent 状态响应"""
    status: str
    graph_initialized: bool
    error: Optional[str] = None


# ── API Endpoints ───────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse, summary="与 Knowledge Agent 对话")
async def chat_with_agent(request: ChatRequest):
    """
    与 Knowledge Agent 进行对话
    
    Agent 会：
    1. 重写查询（query_rewrite）
    2. 确定检索策略（determine_retrieval_strategy）
    3. 检索相关文档切片（doc_retrieval）
    4. 过滤和重新排序（light_filter + rerank）
    5. 生成答案（generate_answer）
    6. 质量评估与重试（check_quality）
    
    - **query**: 用户查询
    - **knowledge_base_ids**: 可选，指定知识库
    - **document_ids**: 可选，指定文档
    - **top_k**: 检索结果数量（默认 10）
    - **retrieval_strategy**: 检索策略（可选）
    """
    from database.mysql.repository.message_repository import MessageRepository
    from agents.knowledge.node.memory_manager import append_to_cache
    import uuid
    
    try:
        from api_service.agent_service import get_knowledge_agent_service
        
        service = get_knowledge_agent_service()
        
        config = {
            "web_search_enabled": request.web_search_enabled,
        }
        if request.top_k is not None:
            config["top_k"] = request.top_k
        
        if request.knowledge_base_ids:
            config["knowledge_base_ids"] = request.knowledge_base_ids
        
        if request.document_ids:
            config["document_ids"] = request.document_ids
        
        if request.retrieval_strategy:
            config["retrieval_strategy"] = request.retrieval_strategy
        
        # 从 session 中获取 user_id（Agent 记忆系统需要）
        from database.mysql.repository.session_repository import SessionRepository
        session_repo = SessionRepository(service.db_client)
        session_data = session_repo.get_by_id(request.session_id)
        user_id = session_data.get('user_id', '') if session_data else ''

        # 调用 Agent（传入 session_id 和 user_id）
        result = await service.invoke(
            request.query,
            config,
            user_id=user_id,
            session_id=request.session_id,
        )

       # 保存用户消息和助手回复到数据库
        try:
            message_repo = MessageRepository(service.db_client)

            if session_data:
                
                # 保存用户消息
                message_repo.create_user_message(
                    session_id=request.session_id,
                    user_id=user_id,
                    content=request.query
                )
                
                # 保存助手回复
                message_repo.create_assistant_message(
                    session_id=request.session_id,
                    user_id=user_id,
                    content=result.get("answer", "")
                )
                
                # 增加会话消息计数（用户消息 + 助手回复 = 2 条）
                session_repo.increment_message_count(request.session_id)
                session_repo.increment_message_count(request.session_id)
                
                logger.info(f"消息已保存：session_id={request.session_id}")

                # 更新内存缓存（避免下次 graph 运行时重新读 DB）
                append_to_cache(request.session_id, [
                    {"role": 0, "content": request.query},
                    {"role": 1, "content": result.get("answer", "")},
                ])
            else:
                logger.warning(f"会话不存在，无法保存消息：session_id={request.session_id}")
        
        except Exception as e:
            logger.warning(f"保存消息失败：{e}")
            # 不抛出异常，继续返回响应
        
        return ChatResponse(
            success=result.get("success", False),
            answer=result.get("answer", ""),
            sources=result.get("sources", []),
            debug=result.get("debug", {}),
            context_blocks=result.get("context_blocks", []),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent 聊天失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent 处理失败：{str(e)}")


@router.get("/status", response_model=AgentStatusResponse, summary="检查 Agent 状态")
async def get_agent_status():
    """
    检查 Knowledge Agent 的运行状态
    """
    try:
        from api_service.agent_service import get_knowledge_agent_service
        
        service = get_knowledge_agent_service()
        graph_initialized = service._agent_graph is not None
        
        return AgentStatusResponse(
            status="ready" if graph_initialized else "initializing",
            graph_initialized=graph_initialized
        )
        
    except Exception as e:
        logger.error(f"获取 Agent 状态失败：{e}")
        return AgentStatusResponse(
            status="error",
            graph_initialized=False,
            error=str(e)
        )


@router.post("/query-expand", summary="查询扩展（测试用）")
async def query_expansion(
    query: str = Body(..., description="原始查询"),
    num_queries: int = Body(3, description="扩展查询数量", ge=1, le=5)
):
    """
    将用户查询扩展为多个相关查询
    
    注意：此功能在 Agent 中已集成，此接口仅用于测试
    """
    # TODO: 实现查询扩展功能
    return {
        "original_query": query,
        "expanded_queries": [query],  # 临时返回原查询
        "note": "查询扩展功能待实现"
    }


@router.post("/rewrite", summary="查询重写（测试用）")
async def query_rewrite(
    query: str = Body(..., description="原始查询"),
    context: Optional[str] = Body(None, description="上下文信息")
):
    """
    重写用户查询，使其更适合检索
    
    注意：此功能在 Agent 中已集成，此接口仅用于测试
    """
    # TODO: 实现查询重写功能
    return {
        "original_query": query,
        "rewritten_query": query,  # 临时返回原查询
        "note": "查询重写功能已集成在 Agent 中"
    }
