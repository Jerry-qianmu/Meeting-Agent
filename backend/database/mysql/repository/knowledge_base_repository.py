# -*- coding: utf-8 -*-
"""
KnowledgeBase 数据访问层
"""

from typing import Optional, Dict, Any, List
import logging
import sys
import os
import uuid

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grand_parent_dir)

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class KnowledgeBaseRepository(BaseRepository):
    """知识库表 Repository"""
    
    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'knowledge_base'
    
    def create_knowledge_base(self, user_id: str, name: str, 
                               description: str = None,
                               collection_name: str = None,
                               embedding_model: str = 'text-embedding-v4') -> Optional[Dict[str, Any]]:
        """
        创建知识库
        
        Args:
            user_id: 用户 ID
            name: 知识库名称
            description: 描述
            collection_name: Milvus collection 名称
            embedding_model: embedding 模型
            
        Returns:
            Dict: 创建的知识库数据，失败返回 None
        """
        kb_id = str(uuid.uuid4())
        data = {
            'kb_uuid': kb_id,
            'user_id': user_id,
            'name': name,
            'description': description,
            'collection_name': collection_name,
            'doc_count': 0,
            'chunk_count': 0,
            'total_tokens': 0,
            'embedding_model': embedding_model,
            'status': 1,  # 1=可用（直接设为可用，无需处理中状态）
            'is_private': True
        }
        
        try:
            result = self.insert(data)
            if result > 0:
                # 直接查询，不使用软删除过滤
                sql = "SELECT * FROM knowledge_base WHERE kb_uuid = %s"
                kb_info = self.fetch_one(sql, (kb_id,))
                if kb_info:
                    logger.info(f"创建知识库成功：{name}, kb_id={kb_id}")
                    return kb_info
                else:
                    # 调试：查询所有记录看看
                    all_kbs = self.fetch_all("SELECT * FROM knowledge_base WHERE user_id = %s", (user_id,))
                    logger.error(f"知识库创建成功但查询失败：{kb_id}, 该用户共有 {len(all_kbs)} 个知识库")
                    return None
            else:
                logger.error(f"知识库插入失败：{name}")
                return None
        except Exception as e:
            logger.error(f"创建知识库异常：{name}, error={e}")
            return None
    
    def get_by_id(self, kb_id: str) -> Optional[Dict[str, Any]]:
        """根据 kb_id 获取知识库"""
        return self.find_one({'kb_uuid': kb_id})
    
    def find_one_by_name(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        """根据 user_id 和 name 查找知识库（检查重复）"""
        sql = """
            SELECT * FROM knowledge_base
            WHERE user_id = %s AND name = %s AND deleted_at IS NULL
            LIMIT 1
        """
        return self.fetch_one(sql, (user_id, name))
    
    def get_user_knowledge_bases(self, user_id: str, 
                                  status: int = None,
                                  limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取用户的所有知识库
        
        Args:
            user_id: 用户 ID
            status: 状态筛选
            limit: 限制数量
            
        Returns:
            List[Dict]: 知识库列表
        """
        conditions = {'user_id': user_id}
        if status is not None:
            conditions['status'] = status
        
        return self.find_by(
            conditions,
            order_by='created_at DESC',
            limit=limit
        )
    
    def update_name(self, kb_id: str, name: str) -> int:
        """更新知识库名称"""
        return self.update({'kb_uuid': kb_id}, {'name': name})
    
    def update_description(self, kb_id: str, description: str) -> int:
        """更新知识库描述"""
        return self.update({'kb_uuid': kb_id}, {'description': description})
    
    def update_collection_name(self, kb_id: str, collection_name: str) -> int:
        """更新 collection 名称"""
        return self.update({'kb_uuid': kb_id}, {'collection_name': collection_name})
    
    def increment_doc_count(self, kb_id: str) -> int:
        """增加文档计数"""
        return self.execute(
            "UPDATE knowledge_base SET doc_count = doc_count + 1 WHERE kb_uuid = %s",
            (kb_id,)
        )
    
    def decrement_doc_count(self, kb_id: str) -> int:
        """减少文档计数"""
        return self.execute(
            "UPDATE knowledge_base SET doc_count = GREATEST(doc_count - 1, 0) WHERE kb_uuid = %s",
            (kb_id,)
        )
    
    def add_chunk_count(self, kb_id: str, count: int) -> int:
        """增加切片计数"""
        return self.execute(
            "UPDATE knowledge_base SET chunk_count = chunk_count + %s WHERE kb_uuid = %s",
            (count, kb_id)
        )
    
    def add_token_count(self, kb_id: str, tokens: int) -> int:
        """增加 token 计数"""
        return self.execute(
            "UPDATE knowledge_base SET total_tokens = total_tokens + %s WHERE kb_uuid = %s",
            (tokens, kb_id)
        )
    
    def update_stats(self, kb_id: str, doc_count: int = None,
                     chunk_count: int = None, total_tokens: int = None) -> int:
        """更新统计信息"""
        data = {}
        if doc_count is not None:
            data['doc_count'] = doc_count
        if chunk_count is not None:
            data['chunk_count'] = chunk_count
        if total_tokens is not None:
            data['total_tokens'] = total_tokens
        
        return self.update({'kb_uuid': kb_id}, data)
    
    def mark_ready(self, kb_id: str) -> int:
        """标记知识库为可用状态"""
        return self.update({'kb_uuid': kb_id}, {'status': 1})
    
    def mark_processing(self, kb_id: str) -> int:
        """标记知识库为处理中"""
        return self.update({'kb_uuid': kb_id}, {'status': 2})
    
    def disable_knowledge_base(self, kb_id: str) -> int:
        """禁用知识库"""
        return self.update({'kb_uuid': kb_id}, {'status': 0})
    
    def delete_knowledge_base(self, kb_id: str) -> int:
        """删除知识库"""
        return self.delete({'kb_uuid': kb_id})
    
    def get_kb_count(self, user_id: str) -> int:
        """获取用户的知识库数量"""
        return self.count({'user_id': user_id})
    
    def list_knowledge_bases(self, status: int = None, 
                             limit: int = 100,
                             offset: int = 0) -> List[Dict[str, Any]]:
        """
        列出所有知识库（不分用户）
        
        Args:
            status: 状态筛选（可选）
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            List[Dict]: 知识库列表
        """
        conditions = {}
        if status is not None:
            conditions['status'] = status
        
        return self.find_by(
            conditions,
            order_by='created_at DESC',
            limit=limit,
            offset=offset
        )
    
    def get_all_knowledge_bases(self, status: int = 1, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        获取所有可用的知识库（用于跨知识库检索）
        
        Args:
            status: 状态筛选，默认只获取可用状态（status=1）
            limit: 限制数量
            
        Returns:
            List[Dict]: 知识库列表
        """
        sql = """
            SELECT kb_uuid, name, collection_name, user_id, status
            FROM knowledge_base
            WHERE status = %s AND deleted_at IS NULL AND collection_name IS NOT NULL
            ORDER BY created_at DESC
            LIMIT %s
        """
        return self.fetch_all(sql, (status, limit))
    
    def search_knowledge_bases(self, user_id: str, keyword: str,
                                limit: int = 20) -> List[Dict[str, Any]]:
        """搜索知识库"""
        sql = """
            SELECT * FROM knowledge_base
            WHERE user_id = %s AND (name LIKE %s OR description LIKE %s)
            AND status != 0
            ORDER BY created_at DESC
            LIMIT %s
        """
        params = (user_id, f'%{keyword}%', f'%{keyword}%', limit)
        return self.fetch_all(sql, params)
