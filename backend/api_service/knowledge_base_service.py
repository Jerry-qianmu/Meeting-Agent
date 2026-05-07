# -*- coding: utf-8 -*-
"""
知识库业务服务
负责知识库创建、管理、Milvus collection 管理
"""

import logging
import os
import sys
import uuid
from typing import Optional, Dict, Any, List

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.insert(0, parent_dir)

from database.mysql.repository.knowledge_base_repository import KnowledgeBaseRepository
from database.milvus.milvus_service import MilvusService

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """知识库服务"""
    
    def __init__(self, db_client):
        """
        初始化知识库服务
        
        Args:
            db_client: MySQL 数据库客户端
        """
        self.kb_repo = KnowledgeBaseRepository(db_client)
        self.milvus_service = MilvusService()
    
    def create_knowledge_base(
        self,
        user_id: str,
        name: str,
        description: str = None,
        embedding_model: str = 'text-embedding-v4',
        embedding_dimension: int = 768
    ) -> Optional[Dict[str, Any]]:
        """
        创建知识库
        
        Args:
            user_id: 用户 ID
            name: 知识库名称
            description: 描述
            embedding_model: embedding 模型
            embedding_dimension: 向量维度
            
        Returns:
            Dict: 创建的知识库信息，失败返回 None
        """
        # 检查是否已存在同名知识库
        existing = self.kb_repo.find_one_by_name(user_id, name)
        if existing:
            logger.warning(f"知识库名称已存在：{name}, user_id={user_id}")
            return None
        
        # 生成唯一的 collection 名称
        collection_name = self._generate_collection_name(user_id, name)
        
        # 1. 创建 MySQL 记录
        kb_info = self.kb_repo.create_knowledge_base(
            user_id=user_id,
            name=name,
            description=description,
            collection_name=collection_name,
            embedding_model=embedding_model
        )
        
        # 检查是否创建成功
        if not kb_info:
            logger.error(f"MySQL 知识库创建失败：{name}")
            return None
            
        kb_id = kb_info['kb_uuid']
        
        # 2. 创建 Milvus collection
        try:
            self.milvus_service.get_or_create_collection(
                collection_name=collection_name,
                dim=embedding_dimension,
                metadata_fields=[
                    {"key": "kb_id", "fulltext": False, "index": True},
                    # doc_id 已内置，不需要重复添加
                    {"key": "chunk_order", "fulltext": False, "index": False},
                ]
            )
            logger.info(f"Milvus collection 创建成功：{collection_name}")
        except Exception as e:
            logger.error(f"Milvus collection 创建失败：{e}")
            # 回滚：删除 MySQL 记录
            try:
                self.kb_repo.delete_knowledge_base(kb_id)
            except Exception as rollback_error:
                logger.error(f"回滚删除失败：{rollback_error}")
            raise Exception(f"创建知识库失败：{e}")
        
        logger.info(f"知识库创建成功：{name}, kb_id={kb_id}")
        
        # 调试：立即查询确认数据已写入
        verify_kb = self.kb_repo.get_by_id(kb_id)
        if verify_kb:
            logger.info(f"验证查询成功：{verify_kb}")
        else:
            logger.error(f"验证查询失败：知识库 {kb_id} 不存在！")
        
        return kb_info
    
    def get_knowledge_base(self, kb_id: str) -> Optional[Dict[str, Any]]:
        """
        获取知识库信息
        
        Args:
            kb_id: 知识库 ID
            
        Returns:
            Dict: 知识库信息
        """
        return self.kb_repo.get_by_id(kb_id)
    
    def get_user_knowledge_bases(
        self,
        user_id: str,
        status: int = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取用户的所有知识库
        
        Args:
            user_id: 用户 ID
            status: 状态筛选
            limit: 限制数量
            
        Returns:
            List[Dict]: 知识库列表
        """
        return self.kb_repo.get_user_knowledge_bases(user_id, status, limit)
    
    def update_knowledge_base(
        self,
        kb_id: str,
        name: str = None,
        description: str = None
    ) -> int:
        """
        更新知识库信息
        
        Args:
            kb_id: 知识库 ID
            name: 新名称
            description: 新描述
            
        Returns:
            int: 影响的行数
        """
        affected_rows = 0
        if name:
            affected_rows += self.kb_repo.update_name(kb_id, name)
        if description:
            affected_rows += self.kb_repo.update_description(kb_id, description)
        return affected_rows
    
    def delete_knowledge_base(self, kb_id: str) -> bool:
        """
        删除知识库（包括 Milvus collection）
        
        Args:
            kb_id: 知识库 ID
            
        Returns:
            bool: 是否删除成功
        """
        kb = self.kb_repo.get_by_id(kb_id)
        if not kb:
            return False
        
        collection_name = kb.get('collection_name')
        
        # 1. 删除 Milvus collection
        if collection_name:
            try:
                self.milvus_service.delete_collection(collection_name)
                logger.info(f"Milvus collection 删除成功：{collection_name}")
            except Exception as e:
                logger.error(f"Milvus collection 删除失败：{e}")
        
        # 2. 删除 MySQL 记录
        self.kb_repo.delete_knowledge_base(kb_id)
        
        logger.info(f"知识库删除成功：{kb_id}")
        return True
    
    def search_knowledge_bases(
        self,
        user_id: str,
        keyword: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        搜索知识库
        
        Args:
            user_id: 用户 ID
            keyword: 搜索关键词
            limit: 限制数量
            
        Returns:
            List[Dict]: 知识库列表
        """
        return self.kb_repo.search_knowledge_bases(user_id, keyword, limit)
    
    def get_kb_stats(self, kb_id: str) -> Dict[str, Any]:
        """
        获取知识库统计信息
        
        Args:
            kb_id: 知识库 ID
            
        Returns:
            Dict: 统计信息
        """
        kb = self.kb_repo.get_by_id(kb_id)
        if not kb:
            return {}
        
        # 获取文档数量
        from database.mysql.repository.document_repository import DocumentRepository
        from database.mysql.repository.chunk_repository import ChunkRepository
        
        # 需要 db_client，这里简化处理
        doc_count = kb.get('doc_count', 0)
        chunk_count = kb.get('chunk_count', 0)
        total_tokens = kb.get('total_tokens', 0)
        
        return {
            'kb_id': kb_id,
            'name': kb.get('name'),
            'doc_count': doc_count,
            'chunk_count': chunk_count,
            'total_tokens': total_tokens,
            'embedding_model': kb.get('embedding_model'),
            'collection_name': kb.get('collection_name'),
            'embedding_dimension': 768,  # 默认值，后续可以从配置读取
            'status': kb.get('status'),
            'milvus_chunk_count': chunk_count  # Milvus 中的切片数（暂与 MySQL 一致）
        }
    
    def _generate_collection_name(self, user_id: str, name: str) -> str:
        """
        生成唯一的 Milvus collection 名称
        
        Args:
            user_id: 用户 ID
            name: 知识库名称
            
        Returns:
            str: collection 名称
        """
        # 清理名称：只保留字母、数字和下划线
        clean_name = "".join(
            c.replace(' ', '_') if c.isalnum() or c in ['_', '-'] else ''
            for c in name.lower()
        )
        short_uuid = str(uuid.uuid4())[:8]
        return f"kb_{user_id[:8]}_{clean_name}_{short_uuid}"
