# -*- coding: utf-8 -*-
"""
知识库 API 控制器
提供知识库的 CRUD 接口
"""

import logging
import os
import sys
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.insert(0, parent_dir)

from api_service.knowledge_base_service import KnowledgeBaseService
from database.mysql.mysql_client import get_db_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-base", tags=["知识库"])


# ── Request/Response Models ─────────────────────────────────────────────────

class CreateKnowledgeBaseRequest(BaseModel):
    """创建知识库请求"""
    name: str = Field(..., description="知识库名称", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="知识库描述", max_length=500)
    embedding_model: str = Field(default="text-embedding-v4", description="Embedding 模型")
    embedding_dimension: int = Field(default=768, description="向量维度")
    user_id: Optional[str] = Field(None, description="用户 ID，如不提供则使用默认值")


class UpdateKnowledgeBaseRequest(BaseModel):
    """更新知识库请求"""
    name: Optional[str] = Field(None, description="新名称", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="新描述", max_length=500)


class KnowledgeBaseResponse(BaseModel):
    """知识库响应"""
    kb_uuid: str
    user_id: str
    name: str
    description: Optional[str]
    collection_name: str
    doc_count: int
    chunk_count: int
    total_tokens: int
    embedding_model: str
    status: int
    is_private: bool
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class KnowledgeBaseListResponse(BaseModel):
    """知识库列表响应"""
    total: int
    items: list


# ── Dependency ──────────────────────────────────────────────────────────────

def get_knowledge_base_service():
    """获取知识库服务"""
    db_client = get_db_client()
    return KnowledgeBaseService(db_client)


# ── API Endpoints ───────────────────────────────────────────────────────────

@router.post("", response_model=KnowledgeBaseResponse, summary="创建知识库")
async def create_knowledge_base(
    request: CreateKnowledgeBaseRequest,
    background_tasks: BackgroundTasks,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
):
    """
    创建新的知识库
    
    - **name**: 知识库名称
    - **description**: 知识库描述（可选）
    - **embedding_model**: Embedding 模型（默认 text-embedding-v4）
    - **embedding_dimension**: 向量维度（默认 768）
    - **user_id**: 用户 ID（必需，从 JWT Token 中获取）
    
    创建后会同时：
    1. 在 MySQL 中创建知识库记录
    2. 在 Milvus 中创建对应的 collection
    """
    user_id = request.user_id
    if not user_id:
        logger.error("创建知识库失败：user_id 不能为空")
        raise HTTPException(status_code=400, detail="user_id 不能为空，请先登录")
    
    try:
        kb_info = service.create_knowledge_base(
            user_id=user_id,
            name=request.name,
            description=request.description,
            embedding_model=request.embedding_model,
            embedding_dimension=request.embedding_dimension
        )
        
        # 检查是否创建成功
        if not kb_info:
            # 检查是否是因为名称重复
            existing = service.kb_repo.find_one_by_name(user_id, request.name)
            if existing:
                logger.error(f"创建知识库失败：名称 '{request.name}' 已存在")
                raise HTTPException(status_code=400, detail=f"知识库名称 '{request.name}' 已存在，请使用其他名称")
            else:
                logger.error(f"创建知识库失败：{request.name}，数据库操作失败")
                raise HTTPException(status_code=500, detail="创建知识库失败，请检查数据库连接")
        
        return kb_info
    except ValueError as e:
        logger.error(f"创建知识库参数错误：{e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建知识库失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建知识库失败：{str(e)}")


@router.get("", response_model=KnowledgeBaseListResponse, summary="获取知识库列表")
async def list_knowledge_bases(
    user_id: Optional[str] = None,
    status: Optional[int] = None,
    limit: int = 100,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
):
    """
    获取知识库列表
    
    - **user_id**: 用户 ID（从 JWT Token 中获取，必需）
    - **status**: 状态筛选（可选）
    - **limit**: 返回数量限制（默认 100）
    """
    if not user_id:
        logger.error("获取知识库列表失败：user_id 不能为空")
        raise HTTPException(status_code=400, detail="user_id 不能为空，请先登录")
    
    try:
        kb_list = service.get_user_knowledge_bases(user_id=user_id, status=status, limit=limit)
        logger.info(f"获取知识库列表：user_id={user_id}, 数量={len(kb_list)}")
        # 调试日志
        if kb_list:
            logger.info(f"知识库列表：{[kb.get('name') for kb in kb_list]}")
            # 调试：查看第一个知识库的完整数据
            logger.info(f"第一个知识库字段：{list(kb_list[0].keys()) if kb_list else 'none'}")
        return {
            "total": len(kb_list),
            "items": kb_list
        }
    except Exception as e:
        logger.error(f"获取知识库列表失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取知识库列表失败：{str(e)}")


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse, summary="获取知识库详情")
async def get_knowledge_base(
    kb_id: str,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
):
    """
    获取指定知识库的详细信息
    
    - **kb_id**: 知识库 ID（UUID 格式）
    """
    try:
        kb_info = service.get_knowledge_base(kb_id)
        if not kb_info:
            raise HTTPException(status_code=404, detail=f"知识库不存在：{kb_id}")
        return kb_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库详情失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取知识库详情失败：{str(e)}")


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse, summary="更新知识库")
async def update_knowledge_base(
    kb_id: str,
    request: UpdateKnowledgeBaseRequest,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
):
    """
    更新知识库信息
    
    - **kb_id**: 知识库 ID
    - **name**: 新名称（可选）
    - **description**: 新描述（可选）
    """
    try:
        # 先检查知识库是否存在
        kb_info = service.get_knowledge_base(kb_id)
        if not kb_info:
            raise HTTPException(status_code=404, detail=f"知识库不存在：{kb_id}")
        
        # 更新信息
        service.update_knowledge_base(
            kb_id=kb_id,
            name=request.name,
            description=request.description
        )
        
        # 返回更新后的信息
        updated_kb = service.get_knowledge_base(kb_id)
        return updated_kb
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新知识库失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新知识库失败：{str(e)}")


@router.delete("/{kb_id}", summary="删除知识库")
async def delete_knowledge_base(
    kb_id: str,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
):
    """
    删除知识库（包括 MySQL 记录和 Milvus collection）
    
    - **kb_id**: 知识库 ID
    """
    try:
        success = service.delete_knowledge_base(kb_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"知识库不存在：{kb_id}")
        return {"message": "知识库删除成功", "kb_id": kb_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除知识库失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除知识库失败：{str(e)}")


@router.get("/{kb_id}/stats", summary="获取知识库统计信息")
async def get_knowledge_base_stats(
    kb_id: str,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
):
    """
    获取知识库的统计信息（文档数、切片数、Token 数等）
    
    - **kb_id**: 知识库 ID
    """
    try:
        stats = service.get_kb_stats(kb_id)
        if not stats:
            raise HTTPException(status_code=404, detail=f"知识库不存在：{kb_id}")
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库统计失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取知识库统计失败：{str(e)}")


@router.post("/search", response_model=KnowledgeBaseListResponse, summary="搜索知识库")
async def search_knowledge_bases(
    keyword: str,
    user_id: Optional[str] = None,
    limit: int = 20,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
):
    """
    搜索知识库（按名称或描述）
    
    - **keyword**: 搜索关键词
    - **user_id**: 用户 ID（从 JWT Token 中获取，必需）
    - **limit**: 返回数量限制（默认 20）
    """
    if not user_id:
        logger.error("搜索知识库失败：user_id 不能为空")
        raise HTTPException(status_code=400, detail="user_id 不能为空，请先登录")
    
    try:
        kb_list = service.search_knowledge_bases(user_id=user_id, keyword=keyword, limit=limit)
        return {
            "total": len(kb_list),
            "items": kb_list
        }
    except Exception as e:
        logger.error(f"搜索知识库失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"搜索知识库失败：{str(e)}")
