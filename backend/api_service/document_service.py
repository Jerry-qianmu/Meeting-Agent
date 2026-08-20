# -*- coding: utf-8 -*-
"""
文档处理服务
负责 PDF 解析、分块、OSS 上传、MySQL 记录、Milvus 向量存储
"""

import logging
import os
import sys
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.insert(0, parent_dir)

from database.mysql.repository.document_repository import DocumentRepository
from database.mysql.repository.chunk_repository import ChunkRepository
from database.mysql.repository.knowledge_base_repository import KnowledgeBaseRepository
from database.oss.oss_service import get_oss_service
from database.milvus.milvus_service import MilvusService
from service.embedding_service import get_embedding_service
from service.parse import parse_pdf
from service.chunking import chunk_markdown, ChunkGraph
from service.tokenizer import count_tokens
from config.settings import Settings

logger = logging.getLogger(__name__)

# 后台线程池，用于异步处理文档
executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="doc_processor")


class DocumentService:
    """文档处理服务"""
    
    def __init__(self, db_client):
        """
        初始化文档服务
        
        Args:
            db_client: MySQL 数据库客户端
        """
        self.document_repo = DocumentRepository(db_client)
        self.chunk_repo = ChunkRepository(db_client)
        self.kb_repo = KnowledgeBaseRepository(db_client)
        self.oss_service = get_oss_service()
        self.milvus_service = MilvusService()
        self.embedding_service = get_embedding_service()
        
    # 分块配置
        self.chunk_size = 500  # 每个 chunk 的字符数
        self.chunk_overlap = 50  # chunk 之间的重叠字符数（改为 0 禁用重叠）
    
    def upload_and_process_document(
        self,
        kb_id: str,
        user_id: str,
        file_content: bytes,
        original_filename: str,
        title: str = None,
        metadata: dict = None
    ) -> Dict[str, Any]:
        """
        上传文档并异步处理（PDF 解析、分块、向量化）
        
        Args:
            kb_id: 知识库 ID
            user_id: 用户 ID
            file_content: 文件内容
            original_filename: 原始文件名
            title: 文档标题
            metadata: 扩展元数据
            
        Returns:
            Dict: 文档信息
        """
        # 1. 提取文件扩展名
        file_extension = os.path.splitext(original_filename)[1].lower().lstrip('.')
        
        # 2. 获取知识库信息
        kb = self.kb_repo.get_by_id(kb_id)
        if not kb:
            raise ValueError(f"知识库不存在：{kb_id}")
        
        collection_name = kb.get('collection_name')
        embedding_model = kb.get('embedding_model', 'text-embedding-v4')
        
        # 3. 上传到 OSS
        object_key = f"documents/{kb_id}/{original_filename}"
        try:
            oss_path = self.oss_service.upload_bytes(object_key, file_content)
            logger.info(f"OSS 上传成功：{oss_path}")
        except Exception as e:
            logger.error(f"OSS 上传失败：{e}")
            raise Exception(f"文件上传失败：{e}")
        
        # 4. 创建 MySQL 文档记录
        doc_info = self.document_repo.create_document(
            kb_id=kb_id,
            user_id=user_id,
            original_filename=original_filename,
            file_extension=file_extension,
            file_size=len(file_content),
            oss_path=oss_path,
            title=title or os.path.splitext(original_filename)[0],
            oss_bucket=self.oss_service.bucket,
            metadata=metadata
        )
        doc_id = doc_info['doc_uuid']
        logger.info(f"文档记录创建成功：{doc_id}")
        
        # 5. 异步处理文档（解析、分块、向量化）
        # 使用后台线程池异步处理，不阻塞上传请求
        executor.submit(
            self._process_document_async,
            doc_id, kb_id, collection_name, file_extension, oss_path
        )
        
        # 6. 增加知识库文档计数
        self.kb_repo.increment_doc_count(kb_id)
        
        return doc_info
    
    def _process_document_async(self, doc_id: str, kb_id: str, 
                                 collection_name: str, file_extension: str, oss_path: str):
        """
        异步处理文档（后台线程执行）
        
        Args:
            doc_id: 文档 ID
            kb_id: 知识库 ID
            collection_name: Milvus collection 名称
            file_extension: 文件扩展名
            oss_path: OSS 路径
        """
        # 标记为处理中
        self.document_repo.mark_processing(doc_id)
        
        try:
            # 1. 从 OSS 下载文件内容
            file_content = self.oss_service.get_object_bytes(oss_path)
            
            # 2. 解析文档内容
            if file_extension == 'pdf':
                chunks = self._parse_pdf_with_service(doc_id, file_content)
            elif file_extension == 'md':
                chunks = self._parse_markdown(doc_id, file_content, collection_name)
            elif file_extension == 'txt':
                chunks = self._parse_text(file_content)
            else:
                raise ValueError(f"不支持的文件格式：{file_extension}")
            
            logger.info(f"文档解析完成：{len(chunks)} 个 chunk")
            
            # 3. 保存 chunk 到 MySQL 和 Milvus
            self._save_chunks(doc_id, kb_id, collection_name, chunks)
            
            # 4. 更新文档状态
            chunk_count = len(chunks)
            total_tokens = sum(chunk.get('token_count', 0) for chunk in chunks)
            self.document_repo.mark_done(doc_id, chunk_count, total_tokens)
            
            # 5. 更新知识库统计
            self.kb_repo.add_chunk_count(kb_id, chunk_count)
            self.kb_repo.add_token_count(kb_id, total_tokens)
            
            logger.info(f"文档处理完成：{doc_id}, chunks={chunk_count}, tokens={total_tokens}")
            
        except Exception as e:
            logger.error(f"文档处理失败：{e}", exc_info=True)
            self.document_repo.mark_failed(doc_id, str(e))
    
    def _parse_pdf_with_service(self, doc_id: str, file_content: bytes) -> List[Dict[str, Any]]:
        """
        使用 parse.py 中的 parse_pdf 函数解析 PDF
        
        Args:
            doc_id: 文档 ID
            file_content: PDF 文件字节内容
            
        Returns:
            List[Dict]: 切片列表
        """
        doc = self.document_repo.get_by_id(doc_id)
        if not doc:
            raise ValueError(f"文档不存在：{doc_id}")
        
        kb_id = doc.get('kb_uuid')
        kb = self.kb_repo.get_by_id(kb_id)
        collection_name = kb.get('collection_name') if kb else f"kb_{kb_id}"
        
        try:
            # 调用 parse.py 中的 parse_pdf 函数
            chunks, _ = parse_pdf(
                file_content=file_content,
                job_id=f"doc_{doc_id}",
                collection=collection_name,
                file_name=doc.get('original_filename', 'document.pdf'),
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap  # 使用配置的重叠值
            )
            
            # 转换格式，添加 token_count
            result = []
            for chunk in chunks:
                content = chunk.get('content', '')
                
                # 可选：清理 chunk 开头/结尾的重复内容（如页眉/页脚）
                # 如果检测到 chunk 开头有重复的常见模式，可以清理
                content = self._clean_chunk_content(content)
                
                token_count = count_tokens(content)
                result.append({
                    'content': content,
                    'chunk_order': chunk.get('chunk_index', 0),
                    'chunk_id': chunk.get('chunk_id'),
                    'start_char': 0,  # parse_pdf 未提供位置信息
                    'end_char': len(content),
                    'token_count': token_count,
                    'metadata': chunk.get('metadata', {}),
                    'page': chunk.get('metadata', {}).get('page')
                })
            
            return result
            
        except ImportError:
            raise ImportError("请安装 PyMuPDF: pip install PyMuPDF")
        except Exception as e:
            logger.error(f"PDF 解析失败：{e}", exc_info=True)
            raise
    
    def _parse_text(self, file_content: bytes) -> List[Dict[str, Any]]:
        """
        解析文本文件（简单的字符级分块）
        
        Args:
            file_content: 文件字节内容
            
        Returns:
            List[Dict]: 切片列表
        """
        content = file_content.decode('utf-8')
        return self._chunk_document(content)

    def _parse_markdown(self, doc_id: str, file_content: bytes, collection_name: str = "") -> List[Dict[str, Any]]:
        """
        解析 Markdown 文件（层级分块 + 构图）
        富化（description + keywords）放到后台异步执行，不阻塞写入
        """
        content = file_content.decode('utf-8')

        # 1. 分块
        cfg = Settings()
        chunks = chunk_markdown(
            markdown_text=content,
            doc_id=doc_id,
            min_tokens=cfg.md_chunk_min_tokens,
            max_tokens=cfg.md_chunk_max_tokens,
            target_tokens=cfg.md_chunk_target_tokens,
            prepend_heading_path=cfg.md_chunk_prepend_heading,
        )

        if not chunks:
            logger.warning(f"[DocumentService] Markdown 分块结果为空: {doc_id}")
            return []

        # 2. 构建结构图（轻量，同步）
        graph = ChunkGraph()
        graph.build_from_chunks(chunks)
        chunks = graph.enrich_chunk_metadata(chunks)

        # 3. 补充 token_count
        for chunk in chunks:
            if 'token_count' not in chunk or not chunk['token_count']:
                chunk['token_count'] = count_tokens(chunk.get('content', ''))

        logger.info(f"[DocumentService] Markdown 分块完成: {len(chunks)} 个 chunk")

        return chunks

    def _chunk_document(self, content: str) -> List[Dict[str, Any]]:
        """
        文档分块（简单的字符级分块）
        
        Args:
            content: 文档内容
            
        Returns:
            List[Dict]: 分块列表
        """
        chunks = []
        start = 0
        chunk_order = 0
        
        while start < len(content):
            end = start + self.chunk_size
            chunk_text = content[start:end]
            
            # 计算 token 数
            token_count = count_tokens(chunk_text)
            
            chunks.append({
                'content': chunk_text,
                'chunk_order': chunk_order,
                'chunk_id': str(uuid.uuid4()),
                'start_char': start,
                'end_char': end,
                'token_count': token_count,
                'metadata': {},
                'page': None
            })
            
            start = end - self.chunk_overlap
            chunk_order += 1
            
            # 防止死循环
            if end >= len(content):
                break
        
        return chunks
    
    
    def _clean_chunk_content(self, content: str) -> str:
        """
        清理 chunk 内容，去除可能的重复页眉/页脚
        
        Args:
            content: chunk 内容
            
        Returns:
            str: 清理后的内容
        """
        if not content:
            return content
        
        # 去除开头和结尾的纯数字（可能是页码）
        import re
        
        # 去除开头的可能重复内容
        # 例如："第 1 页\n" 或 "1\n"
        content = re.sub(r'^[\d\s]+\n+', '', content)
        
        # 去除结尾的可能重复内容
        content = re.sub(r'[\d\s]+$', '', content)
        
        # 去除开头结尾的空白
        content = content.strip()
        
        return content
    
    def _save_chunks(self, doc_id: str, kb_id: str, 
                     collection_name: str, chunks: List[Dict[str, Any]]):
        """
        保存 chunk 到 MySQL 和 Milvus
        
        Args:
            doc_id: 文档 ID
            kb_id: 知识库 ID
            collection_name: Milvus collection 名称
            chunks: 分块列表
        """
        milvus_chunks = []

        for chunk in chunks:
            chunk_id = chunk.get('chunk_id') or str(uuid.uuid4())
            page_number = chunk.get('page')
            heading_path = chunk.get('heading_path', [])
            section_title = heading_path[-1] if heading_path else None

            # 保存到 MySQL（description/keywords/heading_path 存入独立列）
            db_chunk_id = self.chunk_repo.create_chunk(
                doc_id=doc_id,
                kb_id=kb_id,
                content=chunk['content'],
                chunk_order=chunk['chunk_order'],
                token_count=chunk['token_count'],
                start_char=chunk.get('start_char', 0),
                end_char=chunk.get('end_char', len(chunk['content'])),
                page_number=page_number,
                section_title=section_title,
                description=chunk.get('description'),
                keywords=chunk.get('keywords'),
                heading_path=heading_path if heading_path else None,
                metadata=chunk.get('metadata'),
                chunk_id=chunk_id,
            )
            # 写回 MySQL 的 chunk_uuid，供后续富化回写使用
            chunk['db_chunk_id'] = db_chunk_id

            # 主 collection 只存原文（description 在独立 collection 中）
            milvus_chunks.append({
                'chunk_id': chunk_id,
                'doc_id': doc_id,
                'job_id': f"doc_{doc_id}",
                'chunk_index': chunk['chunk_order'],
                'content': chunk['content'],
                'metadata': {
                    'kb_id': kb_id,
                    'doc_id': doc_id,
                    'chunk_order': chunk['chunk_order'],
                    'page': page_number,
                }
            })
        
        # 2. 批量上传到 Milvus（包含向量化）
        if milvus_chunks:
            vector_dim = self.embedding_service.dimension
            self.milvus_service.upsert_chunks(
                collection_name=collection_name,
                chunks=milvus_chunks,
                vector_dim=vector_dim,
                embedding_model='text-embedding-v4'
            )

        logger.info(f"Chunk 保存完成：MySQL={len(chunks)}, Milvus={len(chunks)}")
    
    def retry_document(self, doc_id: str) -> bool:
        """
        重试处理失败的文档
        
        Args:
            doc_id: 文档 ID
            
        Returns:
            bool: 是否成功
        """
        doc = self.document_repo.get_by_id(doc_id)
        if not doc:
            logger.error(f"文档不存在：{doc_id}")
            return False
        
        kb_id = doc.get('kb_uuid')
        kb = self.kb_repo.get_by_id(kb_id)
        collection_name = kb.get('collection_name') if kb else None
        file_extension = doc.get('file_extension')
        oss_path = doc.get('oss_path')
        
        if not collection_name:
            logger.error(f"知识库不存在或没有 collection 名称")
            return False
        
        # 重新处理
        executor.submit(
            self._process_document_async,
            doc_id, kb_id, collection_name, file_extension, oss_path
        )
        
        return True
    
    def delete_document(self, doc_id: str) -> bool:
        """
        删除文档（级联删除 MySQL 和 Milvus 数据）
        
        Args:
            doc_id: 文档 ID
            
        Returns:
            bool: 是否成功
        """
        # 1. 获取文档信息
        doc = self.document_repo.get_by_id(doc_id)
        if not doc:
            logger.error(f"文档不存在：{doc_id}")
            return False
        
        kb_id = doc.get('kb_uuid')
        kb = self.kb_repo.get_by_id(kb_id)
        collection_name = kb.get('collection_name') if kb else None
        oss_path = doc.get('oss_path')
        doc_tokens = doc.get('total_tokens', 0)
        
        try:
            # 2. 删除 OSS 文件
            if oss_path:
                self.oss_service.delete_file(oss_path)
                logger.info(f"已删除 OSS 文件：{oss_path}")
            
            # 3. 删除 MySQL 中的 chunk 记录
            self.chunk_repo.delete_by_doc(doc_id)
            logger.info(f"已删除 chunk: doc_id={doc_id}")
            
            # 4. 删除 MySQL 中的文档记录
            self.document_repo.delete_document(doc_id)
            logger.info(f"已删除文档：doc_id={doc_id}")
            
            # 5. 删除 Milvus 中的向量数据
            if collection_name:
                self.milvus_service.delete_by_doc_id(collection_name, doc_id)
                logger.info(f"已删除 Milvus 数据：doc_id={doc_id}, collection={collection_name}")
            
            # 6. 更新知识库统计信息
            if kb_id:
                self._update_kb_stats_after_delete(kb_id, doc_tokens)
                logger.info(f"已更新知识库统计：kb_id={kb_id}")
            
            logger.info(f"文档删除成功：doc_id={doc_id}")
            return True
            
        except Exception as e:
            logger.error(f"文档删除失败：doc_id={doc_id}, error={e}")
            return False
    
    def _update_kb_stats_after_delete(self, kb_id: str, doc_tokens: int) -> None:
        """删除文档后更新知识库统计"""
        # 重新计算知识库的文档数、切片数、Token 数
        from database.mysql.repository.document_repository import DocumentRepository
        from database.mysql.repository.chunk_repository import ChunkRepository
        
        doc_repo = DocumentRepository(self.db_client)
        chunk_repo = ChunkRepository(self.db_client)
        
        # 获取剩余文档数
        docs = doc_repo.get_by_kb(kb_id, status=2, limit=10000)
        new_doc_count = len(docs)
        
        # 获取剩余切片总数和 Token 总数
        new_chunk_count = 0
        new_total_tokens = 0
        
        for d in docs:
            doc_chunks = chunk_repo.get_by_doc(d['doc_uuid'])
            new_chunk_count += len(doc_chunks)
            for c in doc_chunks:
                new_total_tokens += c.get('token_count', 0)
        
        # 更新知识库记录
        self.kb_repo.update(kb_id, {
            'doc_count': new_doc_count,
            'chunk_count': new_chunk_count,
            'total_tokens': new_total_tokens
        })
        
        logger.info(f"知识库统计已更新：docs={new_doc_count}, chunks={new_chunk_count}, tokens={new_total_tokens}")
