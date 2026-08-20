# -*- coding: utf-8 -*-
"""
文档 API 控制器
提供文档上传、查询、删除等接口
"""

import logging
import os
import sys
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel, Field

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.insert(0, parent_dir)

from api_service.document_service import DocumentService
from database.mysql.mysql_client import get_db_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document", tags=["文档"])


# ── Request/Response Models ─────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    """文档响应"""
    doc_uuid: str
    kb_uuid: str
    user_id: str
    title: Optional[str]
    original_filename: str
    file_extension: str
    file_size: int
    oss_path: str
    oss_bucket: Optional[str]
    chunk_count: int
    total_tokens: int
    status: int
    version: int
    metadata: Optional[str]
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    total: int
    items: list


class DocumentStatusResponse(BaseModel):
    """文档处理状态响应"""
    doc_id: str
    status: int
    status_text: str
    processed_chunks: int
    total_chunks: int
    progress_percent: float


class ChunkResponse(BaseModel):
    """切片响应"""
    chunk_uuid: str
    doc_uuid: str
    kb_uuid: str
    content: str
    chunk_order: int
    page_number: Optional[int]
    token_count: int
    metadata: Optional[str]
    created_at: str


class ChunkWithVectorResponse(BaseModel):
    """带向量的切片响应"""
    chunk_uuid: str
    doc_uuid: str
    kb_uuid: str
    content: str
    chunk_order: int
    page_number: Optional[int]
    token_count: int
    metadata: Optional[str]
    vector_dimension: Optional[int]
    vector_preview: Optional[list]  # 前 10 个向量值作为预览
    created_at: str


class ChunkListResponse(BaseModel):
    """切片列表响应"""
    total: int
    items: list


class ChunkVectorListResponse(BaseModel):
    """带向量的切片列表响应"""
    total: int
    items: list


# ── Dependency ──────────────────────────────────────────────────────────────

def get_document_service():
    """获取文档服务"""
    db_client = get_db_client()
    return DocumentService(db_client)


# ── API Endpoints ───────────────────────────────────────────────────────────

@router.post("/upload", response_model=DocumentResponse, summary="上传文档到知识库")
async def upload_document(
    kb_id: str = Form(..., description="知识库 ID"),
    file: UploadFile = File(..., description="要上传的文件"),
    title: Optional[str] = Form(None, description="文档标题（可选，默认使用文件名）"),
    user_id: Optional[str] = Form(None, description="用户 ID（必需，从 JWT Token 中获取）"),
    service: DocumentService = Depends(get_document_service)
):
    """
    上传文档到指定的知识库
    
    支持的文件格式：
    - PDF (.pdf)
    - 文本文件 (.txt, .md)
    
    上传后会异步处理：
    1. 文件保存到 OSS
    2. 在 MySQL 中创建文档记录
    3. 解析文档内容
    4. 文档分块
    5. 保存 chunk 到 MySQL
    6. 向量化并上传到 Milvus
    """
    # 检查 user_id
    if not user_id:
        logger.error("上传文档失败：user_id 不能为空")
        raise HTTPException(status_code=400, detail="user_id 不能为空，请先登录")
    
    # 检查文件扩展名
    file_extension = os.path.splitext(file.filename)[1].lower().lstrip('.')
    supported_formats = ['pdf', 'txt', 'md']
    
    if file_extension not in supported_formats:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式：{file_extension}。支持：{', '.join(supported_formats)}"
        )
    
    # 检查文件大小（50MB 限制）
    max_size = 50 * 1024 * 1024  # 50MB
    try:
        file_content = await file.read()
    except Exception as e:
        logger.error(f"读取文件失败：{e}")
        raise HTTPException(status_code=400, detail=f"读取文件失败：{str(e)}")
    
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制：{len(file_content) / 1024 / 1024:.2f}MB > 50MB"
        )
    
    # 已在上文检查 user_id，直接使用
    uid = user_id
    
    try:
        # 上传并处理文档
        doc_info = service.upload_and_process_document(
            kb_id=kb_id,
            user_id=uid,
            file_content=file_content,
            original_filename=file.filename,
            title=title
        )
        
        return doc_info
        
    except ValueError as e:
        logger.error(f"上传文档参数错误：{e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"上传文档失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"上传文档失败：{str(e)}")


@router.get("", response_model=DocumentListResponse, summary="获取文档列表")
async def list_documents(
    kb_id: Optional[str] = None,
    user_id: Optional[str] = None,
    status: Optional[int] = None,
    limit: int = 100,
    service: DocumentService = Depends(get_document_service)
):
    """
    获取文档列表
    
    - **kb_id**: 知识库 ID（可选）
    - **user_id**: 用户 ID（从 JWT Token 中获取，必需）
    - **status**: 状态筛选（可选）
    - **limit**: 返回数量限制（默认 100）
    """
    if not user_id:
        logger.error("获取文档列表失败：user_id 不能为空")
        raise HTTPException(status_code=400, detail="user_id 不能为空，请先登录")
    
    try:
        # 根据 kb_id 获取文档
        if kb_id:
            # 先检查知识库是否存在
            kb = service.kb_repo.get_by_id(kb_id)
            if not kb:
                raise HTTPException(status_code=404, detail="知识库不存在")
            
            doc_list = service.document_repo.get_by_kb(kb_id, status, limit)
        else:
            doc_list = service.document_repo.get_user_documents(user_id, status, limit)
        
        return {
            "total": len(doc_list),
            "items": doc_list
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档列表失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取文档列表失败：{str(e)}")


@router.get("/{doc_id}", response_model=DocumentResponse, summary="获取文档详情")
async def get_document(
    doc_id: str,
    service: DocumentService = Depends(get_document_service)
):
    """
    获取指定文档的详细信息
    
    - **doc_id**: 文档 ID（UUID 格式）
    """
    try:
        doc_info = service.document_repo.get_by_id(doc_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
        return doc_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档详情失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取文档详情失败：{str(e)}")


@router.get("/{doc_id}/status", response_model=DocumentStatusResponse, summary="获取文档处理状态")
async def get_document_status(
    doc_id: str,
    service: DocumentService = Depends(get_document_service)
):
    """
    获取文档的处理状态和进度
    
    - **doc_id**: 文档 ID
    """
    try:
        doc_info = service.document_repo.get_by_id(doc_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
        
        # 状态映射
        status_map = {
            0: "pending",
            1: "processing",
            2: "done",
            3: "failed"
        }
        
        status = doc_info.get('status', 0)
        total_chunks = doc_info.get('total_chunks', 0) or 0
        processed_chunks = doc_info.get('processed_chunks', 0) or 0
        
        # 计算进度
        if total_chunks > 0:
            progress = (processed_chunks / total_chunks) * 100
        else:
            progress = 0.0 if status == 0 else 100.0
        
        return {
            "doc_id": doc_id,
            "status": status,
            "status_text": status_map.get(status, "unknown"),
            "processed_chunks": processed_chunks,
            "total_chunks": total_chunks,
            "progress_percent": round(progress, 2)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档状态失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取文档状态失败：{str(e)}")


@router.delete("/{doc_id}", summary="删除文档")
async def delete_document(
    doc_id: str,
    service: DocumentService = Depends(get_document_service)
):
    """
    删除文档（包括 OSS 文件、MySQL 记录、Milvus 数据）
    
    - **doc_id**: 文档 ID
    """
    try:
        doc_info = service.document_repo.get_by_id(doc_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
        
        kb_id = doc_info.get('kb_uuid')
        
        # 1. 删除 OSS 文件
        try:
            service.oss_service.delete_document(kb_id, doc_id)
            logger.info(f"OSS 文件删除成功：{doc_id}")
        except Exception as e:
            logger.warning(f"OSS 文件删除失败：{e}")
        
        # 2. 删除 Milvus 数据
        kb = service.kb_repo.get_by_id(kb_id)
        if kb:
            collection_name = kb.get('collection_name')
            try:
                service.milvus_service.delete_by_doc_id(collection_name, doc_id)
                logger.info(f"Milvus 数据删除成功：{doc_id}")
            except Exception as e:
                logger.warning(f"Milvus 数据删除失败：{e}")
        
        # 3. 删除 MySQL 记录（包括 chunk）
        service.chunk_repo.delete_by_doc(doc_id)
        service.document_repo.delete_document(doc_id)
        
        # 4. 更新知识库统计
        service.kb_repo.decrement_doc_count(kb_id)
        
        logger.info(f"文档删除成功：{doc_id}")
        return {"message": "文档删除成功", "doc_id": doc_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除文档失败：{str(e)}")


@router.post("/{doc_id}/retry", response_model=DocumentResponse, summary="重试处理失败的文档")
async def retry_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    service: DocumentService = Depends(get_document_service)
):
    """
    重新处理失败的文档
    
    - **doc_id**: 文档 ID
    """
    try:
        doc_info = service.document_repo.get_by_id(doc_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
        
        # 检查文档状态
        if doc_info.get('status') != 3:
            raise HTTPException(
                status_code=400,
                detail="只有处理失败的文档才能重试"
            )
        
        kb_id = doc_info.get('kb_uuid')
        kb = service.kb_repo.get_by_id(kb_id)
        collection_name = kb.get('collection_name') if kb else None
        file_extension = doc_info.get('file_extension')
        
        if not collection_name:
            raise HTTPException(status_code=400, detail="知识库不存在或没有 collection 名称")
        
        # 重新处理
        service._process_document_async(doc_id, kb_id, collection_name, file_extension)
        
        return service.document_repo.get_by_id(doc_id)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重试文档失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重试文档失败：{str(e)}")


@router.get("/kb/{kb_id}", response_model=DocumentListResponse, summary="获取知识库的文档列表")
async def get_kb_documents(
    kb_id: str,
    status: Optional[int] = None,
    limit: int = 100,
    service: DocumentService = Depends(get_document_service)
):
    """
    获取指定知识库的所有文档
    
    - **kb_id**: 知识库 ID
    - **status**: 状态筛选（可选）
    - **limit**: 返回数量限制（默认 100）
    """
    try:
        # 检查知识库是否存在
        kb = service.kb_repo.get_by_id(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail=f"知识库不存在：{kb_id}")
        
        doc_list = service.document_repo.get_by_kb(kb_id, status, limit)
        
        return {
            "total": len(doc_list),
            "items": doc_list
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库文档列表失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取知识库文档列表失败：{str(e)}")


@router.delete("/{doc_id}", summary="删除文档（级联删除 MySQL 和 Milvus 数据）")
async def delete_document(
    doc_id: str,
    service: DocumentService = Depends(get_document_service)
):
    """
    删除指定文档，同时删除：
    - MySQL 中的文档记录
    - MySQL 中的 chunk 记录
    - Milvus 中的向量数据
    
    - **doc_id**: 文档 ID
    """
    try:
        success = service.delete_document(doc_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"文档删除失败，可能不存在：{doc_id}")
        
        return {
            "message": "文档删除成功",
            "doc_id": doc_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除文档失败：{str(e)}")


@router.get("/{doc_id}/chunks", response_model=ChunkListResponse, summary="获取文档的所有切片")
async def get_document_chunks(
    doc_id: str,
    service: DocumentService = Depends(get_document_service)
):
    """
    获取指定文档的所有切片
    
    - **doc_id**: 文档 ID
    """
    try:
        # 验证文档是否存在
        doc = service.document_repo.get_by_id(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
        
        # 获取切片列表
        chunks = service.chunk_repo.get_by_doc(doc_id)
        
        return {
            "total": len(chunks),
            "items": chunks
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档切片失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取文档切片失败：{str(e)}")


@router.get("/{doc_id}/chunks-with-vectors", response_model=ChunkVectorListResponse, summary="获取文档的所有切片（含向量数据）")
async def get_document_chunks_with_vectors(
    doc_id: str,
    service: DocumentService = Depends(get_document_service)
):
    """
    获取指定文档的所有切片，包含 Milvus 中的向量数据
    
    - **doc_id**: 文档 ID
    """
    try:
        # 验证文档是否存在
        doc = service.document_repo.get_by_id(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
        
        kb_id = doc.get('kb_uuid')
        kb = service.kb_repo.get_by_id(kb_id)
        collection_name = kb.get('collection_name') if kb else None
        
        if not collection_name:
            raise HTTPException(status_code=404, detail=f"知识库不存在或没有 collection")
        
        # 获取切片列表
        chunks = service.chunk_repo.get_by_doc(doc_id)
        
        # 从 Milvus 获取向量数据
        result_items = []
        for chunk in chunks:
            # 从 Milvus 查询该 chunk 的向量
            try:
                milvus_data = service.milvus_service.get_chunk_by_id(collection_name, chunk['chunk_uuid'])
                
                if milvus_data:
                    vector = milvus_data.get('dense', [])
                    vector_dim = len(vector) if vector else 0
                    # 只返回前 10 个向量值作为预览
                    vector_preview = vector[:10] if vector else []
                else:
                    vector_dim = 0
                    vector_preview = []
            except Exception as e:
                logger.warning(f"获取 chunk 向量失败：{chunk['chunk_uuid']}, error={e}")
                vector_dim = 0
                vector_preview = []
            
            result_items.append({
                'chunk_uuid': chunk['chunk_uuid'],
                'doc_uuid': chunk['doc_uuid'],
                'kb_uuid': chunk['kb_uuid'],
                'content': chunk['content'],
                'chunk_order': chunk['chunk_order'],
                'page_number': chunk.get('page_number'),
                'token_count': chunk.get('token_count', 0),
                'metadata': chunk.get('metadata'),
                'vector_dimension': vector_dim,
                'vector_preview': vector_preview,
                'created_at': chunk.get('created_at', '')
            })
        
        return {
            "total": len(result_items),
            "items": result_items
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档切片（含向量）失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取文档切片失败：{str(e)}")
