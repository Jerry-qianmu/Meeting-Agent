# -*- coding: utf-8 -*-
"""
Session API 控制器
提供会话管理的 REST API 接口
"""

import logging
import os
import sys
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grand_parent_dir)

from database.mysql.mysql_client import get_db_client
from database.mysql.repository.session_repository import SessionRepository
from database.mysql.repository.message_repository import MessageRepository


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/session", tags=["会话管理"])


# ==================== Pydantic Models ====================

class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    user_id: str = Field(..., description="用户 ID")
    title: Optional[str] = Field(None, description="会话标题", max_length=255)
    knowledge_base_ids: Optional[List[str]] = Field(None, description="默认知识库 ID 列表")
    document_ids: Optional[List[str]] = Field(None, description="默认文档 ID 列表")


class CreateSessionResponse(BaseModel):
    """创建会话响应"""
    success: bool
    session_id: str
    title: str
    created_at: str


class SessionResponse(BaseModel):
    """会话信息响应"""
    session_id: str
    user_id: str
    title: str
    summary: Optional[str]
    status: int
    message_count: int
    token_count: int
    knowledge_base_ids: Optional[List[str]]
    document_ids: Optional[List[str]]
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    """会话列表响应"""
    success: bool
    total: int
    sessions: List[Dict[str, Any]]


class CreateMessageRequest(BaseModel):
    """创建消息请求"""
    session_id: str = Field(..., description="会话 ID")
    user_id: str = Field(..., description="用户 ID")
    role: str = Field(..., description="角色：user/assistant/system/tool")
    content: str = Field(..., description="消息内容", min_length=1, max_length=50000)
    parent_message_id: Optional[str] = Field(None, description="父消息 ID")
    tool_calls: Optional[Dict] = Field(None, description="工具调用信息")
    model: Optional[str] = Field(None, description="使用的模型")
    tokens_prompt: Optional[int] = Field(None, description="prompt token 数")
    tokens_completion: Optional[int] = Field(None, description="completion token 数")
    latency_ms: Optional[int] = Field(None, description="响应耗时 (毫秒)")


class MessageResponse(BaseModel):
    """消息响应"""
    success: bool
    message_id: str
    role: str
    content: str
    created_at: str


class MessageListResponse(BaseModel):
    """消息列表响应"""
    success: bool
    total: int
    messages: List[Dict[str, Any]]


# ==================== Helper Functions ====================

def get_session_repository():
    """获取 Session Repository"""
    db_client = get_db_client()
    return SessionRepository(db_client)


def get_message_repository():
    """获取 Message Repository"""
    db_client = get_db_client()
    return MessageRepository(db_client)


def role_to_int(role: str) -> int:
    """将角色字符串转换为整数"""
    role_map = {
        'user': 0,
        'assistant': 1,
        'system': 2,
        'tool': 3
    }
    return role_map.get(role.lower(), 0)


def int_to_role(role_int: int) -> str:
    """将角色整数转换为字符串"""
    role_map = {
        0: 'user',
        1: 'assistant',
        2: 'system',
        3: 'tool'
    }
    return role_map.get(role_int, 'unknown')


# ==================== Session API Endpoints ====================

@router.post("/create", response_model=CreateSessionResponse, summary="创建新会话")
async def create_session(request: CreateSessionRequest):
    """
    创建新的对话会话
    
    - **user_id**: 用户 ID
    - **title**: 会话标题（可选）
    - **knowledge_base_ids**: 默认关联的知识库 ID 列表（可选）
    - **document_ids**: 默认关联的文档 ID 列表（可选）
    """
    try:
        repo = get_session_repository()
        
        # 生成默认标题
        if not request.title:
            request.title = f"对话 {len(request.user_id)} - {len(request.knowledge_base_ids or [])} 知识库"
        
        # 创建会话
        session = repo.create_session(
            user_id=request.user_id,
            title=request.title,
            knowledge_base_ids=request.knowledge_base_ids,
            document_ids=request.document_ids
        )
        
        return CreateSessionResponse(
            success=True,
            session_id=session['session_uuid'],
            title=session['title'],
            created_at=session['created_at']
        )
        
    except Exception as e:
        logger.error(f"创建会话失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建会话失败：{str(e)}")


@router.get("/list", response_model=SessionListResponse, summary="获取用户会话列表")
async def list_user_sessions(
    user_id: str = Query(..., description="用户 ID"),
    status: int = Query(1, description="会话状态（1=进行中，0=归档）"),
    limit: int = Query(50, description="每页数量", ge=1, le=200),
    offset: int = Query(0, description="偏移量", ge=0)
):
    """
    获取用户的会话列表
    
    - **user_id**: 用户 ID
    - **status**: 会话状态（1=进行中，0=归档，默认 1）
    - **limit**: 每页数量（默认 50）
    - **offset**: 偏移量（默认 0）
    """
    try:
        repo = get_session_repository()
        
        sessions = repo.get_user_sessions(
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset
        )
        
        total = repo.get_session_count(user_id, status)
        
        # 格式化输出
        formatted_sessions = []
        for session in sessions:
            formatted_sessions.append({
                'session_id': session['session_uuid'],
                'user_id': session['user_id'],
                'title': session['title'],
                'summary': session.get('summary'),
                'status': session['status'],
                'message_count': session['message_count'],
                'token_count': session['token_count'],
                'knowledge_base_ids': session.get('knowledge_base_ids'),
                'document_ids': session.get('document_ids'),
                'created_at': session['created_at'],
                'updated_at': session['updated_at']
            })
        
        return SessionListResponse(
            success=True,
            total=total,
            sessions=formatted_sessions
        )
        
    except Exception as e:
        logger.error(f"获取会话列表失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取会话列表失败：{str(e)}")


@router.get("/{session_id}", response_model=SessionResponse, summary="获取会话详情")
async def get_session(session_id: str, user_id: Optional[str] = Query(None, description="用户 ID（可选验证）")):
    """
    获取会话的详细信息
    
    - **session_id**: 会话 ID
    - **user_id**: 可选，用于验证会话归属
    """
    try:
        repo = get_session_repository()
        
        session = repo.get_by_id(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        # 可选的用户 ID 验证
        if user_id and session['user_id'] != user_id:
            raise HTTPException(status_code=403, detail="无权访问此会话")
        
        return SessionResponse(
            session_id=session['session_uuid'],
            user_id=session['user_id'],
            title=session['title'],
            summary=session.get('summary'),
            status=session['status'],
            message_count=session['message_count'],
            token_count=session['token_count'],
            knowledge_base_ids=session.get('knowledge_base_ids'),
            document_ids=session.get('document_ids'),
            created_at=session['created_at'],
            updated_at=session['updated_at']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话详情失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取会话详情失败：{str(e)}")


@router.put("/{session_id}/title", response_model=Dict[str, Any], summary="更新会话标题")
async def update_session_title(
    session_id: str,
    title: str = Body(..., description="新标题", max_length=255)
):
    """更新会话标题"""
    try:
        repo = get_session_repository()
        
        rows_affected = repo.update_title(session_id, title)
        
        if rows_affected == 0:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        return {
            'success': True,
            'session_id': session_id,
            'title': title
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新会话标题失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新会话标题失败：{str(e)}")


@router.delete("/{session_id}", response_model=Dict[str, Any], summary="删除会话")
async def delete_session(session_id: str):
    """
    删除会话（硬删除，不可恢复）
    同时删除关联的所有消息
    """
    try:
        session_repo = get_session_repository()
        message_repo = get_message_repository()
        
        # 1. 先删除关联的消息
        messages_deleted = message_repo.delete_messages_by_session(session_id)
        logger.info(f"删除会话 {session_id} 的消息 {messages_deleted} 条")
        
        # 2. 删除会话
        rows_affected = session_repo.delete_session(session_id)
        
        if rows_affected == 0:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        return {
            'success': True,
            'session_id': session_id,
            'messages_deleted': messages_deleted,
            'message': f'会话已删除，同时删除了 {messages_deleted} 条消息'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除会话失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除会话失败：{str(e)}")


# ==================== Message API Endpoints ====================

@router.post("/message/create", response_model=MessageResponse, summary="创建消息")
async def create_message(request: CreateMessageRequest):
    """
    创建消息（用户消息或助手消息）
    
    - **session_id**: 会话 ID
    - **user_id**: 用户 ID
    - **role**: 角色（user/assistant/system/tool）
    - **content**: 消息内容
    - **parent_message_id**: 父消息 ID（可选）
    - **tool_calls**: 工具调用信息（仅 tool 角色需要）
    - **model**: 使用的模型（仅 assistant 角色需要）
    - **tokens_prompt**: prompt token 数（仅 assistant 角色需要）
    - **tokens_completion**: completion token 数（仅 assistant 角色需要）
    - **latency_ms**: 响应耗时（仅 assistant 角色需要）
    """
    try:
        repo = get_message_repository()
        session_repo = get_session_repository()
        
        role_int = role_to_int(request.role)
        parent_id = request.parent_message_id
        
        # 根据角色创建消息
        if role_int == 0:  # user
            message = repo.create_user_message(
                session_id=request.session_id,
                user_id=request.user_id,
                content=request.content,
                parent_id=parent_id
            )
        elif role_int == 1:  # assistant
            message = repo.create_assistant_message(
                session_id=request.session_id,
                user_id=request.user_id,
                content=request.content,
                model=request.model,
                tokens_prompt=request.tokens_prompt,
                tokens_completion=request.tokens_completion,
                latency_ms=request.latency_ms,
                parent_id=parent_id
            )
        elif role_int == 2:  # system
            message = repo.create_system_message(
                session_id=request.session_id,
                user_id=request.user_id,
                content=request.content
            )
        elif role_int == 3:  # tool
            message = repo.create_tool_message(
                session_id=request.session_id,
                user_id=request.user_id,
                content=request.content,
                tool_calls=request.tool_calls
            )
        else:
            raise HTTPException(status_code=400, detail=f"无效的角色：{request.role}")
        
        # 增加会话消息计数
        session_repo.increment_message_count(request.session_id)
        
        return MessageResponse(
            success=True,
            message_id=message['message_uuid'],
            role=request.role,
            content=message['content'],
            created_at=message['created_at']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建消息失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建消息失败：{str(e)}")


@router.get("/message/list", response_model=MessageListResponse, summary="获取会话消息列表")
async def list_session_messages(
    session_id: str = Query(..., description="会话 ID"),
    limit: int = Query(100, description="每页数量", ge=1, le=500),
    offset: int = Query(0, description="偏移量", ge=0)
):
    """
    获取会话的消息列表（按时间顺序）
    
    - **session_id**: 会话 ID
    - **limit**: 每页数量（默认 100）
    - **offset**: 偏移量（默认 0）
    """
    try:
        repo = get_message_repository()
        
        # 获取所有消息
        sql = """
            SELECT * FROM message
            WHERE session_uuid = %s AND deleted_at IS NULL
            ORDER BY created_at ASC
            LIMIT %s OFFSET %s
        """
        messages = repo.fetch_all(sql, (session_id, limit, offset))
        
        # 获取总数
        total = repo.count({'session_uuid': session_id})
        
        # 格式化输出
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                'message_id': msg['message_uuid'],
                'session_id': msg['session_uuid'],
                'user_id': msg['user_id'],
                'role': int_to_role(msg['role']),
                'content': msg['content'],
                'parent_message_id': msg.get('parent_message_id'),
                'tool_calls': msg.get('tool_calls'),
                'model': msg.get('model_used'),
                'tokens_prompt': msg.get('tokens_prompt'),
                'tokens_completion': msg.get('tokens_completion'),
                'tokens_total': msg.get('tokens_total'),
                'latency_ms': msg.get('latency_ms'),
                'status': msg['status'],
                'created_at': msg['created_at']
            })
        
        return MessageListResponse(
            success=True,
            total=total,
            messages=formatted_messages
        )
        
    except Exception as e:
        logger.error(f"获取消息列表失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取消息列表失败：{str(e)}")


@router.post("/message/{message_id}/update", response_model=Dict[str, Any], summary="更新消息")
async def update_message(
    message_id: str,
    content: Optional[str] = Body(None, description="新内容"),
    tokens_prompt: Optional[int] = Body(None, description="prompt token 数"),
    tokens_completion: Optional[int] = Body(None, description="completion token 数"),
    latency_ms: Optional[int] = Body(None, description="响应耗时")
):
    """
    更新消息内容或 token 信息
    """
    try:
        repo = get_message_repository()
        
        # 检查消息是否存在
        existing = repo.get_by_id(message_id)
        if not existing:
            raise HTTPException(status_code=404, detail="消息不存在")
        
        # 更新内容
        if content is not None:
            # 直接更新 content（使用 execute）
            repo.execute(
                "UPDATE message SET content = %s, updated_at = CURRENT_TIMESTAMP WHERE message_uuid = %s",
                (content, message_id)
            )
        
        # 更新 token 信息
        if tokens_prompt is not None or tokens_completion is not None or latency_ms is not None:
            repo.update_token_usage(
                message_id=message_id,
                tokens_prompt=tokens_prompt,
                tokens_completion=tokens_completion,
                latency_ms=latency_ms
            )
        
        return {
            'success': True,
            'message_id': message_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新消息失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新消息失败：{str(e)}")


# ==================== Chat Flow API ====================

@router.post("/chat", summary="完整的聊天流程（创建/更新会话 + 记录消息）")
async def chat_with_session(
    user_id: str = Body(..., description="用户 ID"),
    query: str = Body(..., description="用户问题", min_length=1, max_length=4000),
    session_id: Optional[str] = Body(None, description="会话 ID（不传则创建新会话）"),
    knowledge_base_ids: Optional[List[str]] = Body(None, description="知识库 ID 列表"),
    document_ids: Optional[List[str]] = Body(None, description="文档 ID 列表"),
    top_k: int = Body(10, description="检索结果数量", ge=1, le=50)
):
    """
    完整的聊天流程：
    1. 如果没有 session_id，创建新会话
    2. 记录用户消息
    3. 调用 Agent 处理
    4. 记录助手消息
    5. 返回答案
    
    这是一个集成接口，简化前端调用
    """
    try:
        from api_service.agent_service import get_knowledge_agent_service
        
        # 1. 如果没有 session_id，创建新会话
        if not session_id:
            session_repo = get_session_repository()
            session = session_repo.create_session(
                user_id=user_id,
                title=f"对话 {user_id[:8]}...",
                knowledge_base_ids=knowledge_base_ids,
                document_ids=document_ids
            )
            session_id = session['session_uuid']
        
        # 2. 记录用户消息
        msg_repo = get_message_repository()
        session_repo = get_session_repository()
        user_message = msg_repo.create_user_message(
            session_id=session_id,
            user_id=user_id,
            content=query
        )
        
        # 增加消息计数（用户消息）
        session_repo.increment_message_count(session_id)
        
        # 3. 调用 Agent 处理
        service = get_knowledge_agent_service()
        config = {
            "top_k": top_k,
        }
        if knowledge_base_ids:
            config["knowledge_base_ids"] = knowledge_base_ids
        if document_ids:
            config["document_ids"] = document_ids
        
        # 调用 Agent（不支持 checkpoint）
        result = await service.invoke(query, config, user_id=user_id)
        
        # 4. 记录助手消息
        assistant_message = msg_repo.create_assistant_message(
            session_id=session_id,
            user_id=user_id,
            content=result.get('answer', ''),
            model=result.get('debug', {}).get('retrieval_strategy'),
            latency_ms=result.get('metadata', {}).get('total_duration_ms')
        )
        
        # 增加消息计数（助手消息）
        session_repo.increment_message_count(session_id)
        
        # 5. 返回结果
        return {
            'success': True,
            'session_id': session_id,
            'user_message_id': user_message['message_uuid'],
            'assistant_message_id': assistant_message['message_uuid'],
            'answer': result.get('answer', ''),
            'sources': result.get('sources', []),
            'debug': result.get('debug', {})
        }
        
    except Exception as e:
        logger.error(f"聊天流程失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"聊天处理失败：{str(e)}")
