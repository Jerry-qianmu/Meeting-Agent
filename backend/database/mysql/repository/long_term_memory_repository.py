# -*- coding: utf-8 -*-
"""
长期记忆 Repository
同时支持 MySQL（元数据）和 Milvus（向量检索）
所有 ID 统一使用 CHAR(36) UUID 字符串格式
"""
from typing import Optional, Dict, Any, List
import uuid
import logging
import sys
import os

cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.insert(0, parent_dir)

from mysql_client import MysqlClient
from repository.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class LongTermMemoryRepository(BaseRepository):
    """长期记忆 Repository（MySQL + Milvus，所有 ID 使用 UUID 字符串）"""
    
    def __init__(self, db_client: MysqlClient, milvus_client=None):
        """
        初始化 Repository
        
        Args:
            db_client: MysqlClient 实例
            milvus_client: MilvusClient 实例（可选）
        """
        super().__init__(db_client)
        self.milvus = milvus_client
        self.table_name = 'long_term_memory'
    
    def create_memory(self, user_id: str, memory_type: str, content: str,
                      title: str = None, category: str = None,
                      tags: List[str] = None, importance_score: float = 0.5,
                      confidence_score: float = 0.8, source_type: str = None,
                      source_uuid: str = None) -> Dict[str, Any]:
        """
        创建长期记忆（同时写入 MySQL 和 Milvus）
        
        Args:
            user_id: 用户 ID (UUID 字符串)
            memory_type: 记忆类型（preference/habit/fact/relationship/event）
            content: 记忆内容
            title: 记忆标题
            category: 分类
            tags: 标签列表
            importance_score: 重要性分数（0-1）
            confidence_score: 置信度（0-1）
            source_type: 来源类型
            source_uuid: 来源会话/消息 ID (UUID 字符串)
            
        Returns:
            Dict: 创建的记忆数据
        """
        # 1. 生成唯一 ID（UUID 字符串）
        memory_id = str(uuid.uuid4())
        
        # 2. 准备 MySQL 数据
        data = {
            'memory_id': memory_id,
            'user_id': user_id,
            'memory_type': memory_type,
            'content': content,
            'title': title,
            'category': category,
            'tags': tags,
            'importance_score': importance_score,
            'confidence_score': confidence_score,
            'source_type': source_type,
            'source_uuid': source_uuid,
            'is_active': True
        }
        
        # 3. 插入 MySQL
        self.insert(data)
        logger.info(f"创建长期记忆：{memory_id} ({memory_type})")
        
        # 4. 同步到 Milvus（如果可用）
        milvus_id = None
        if self.milvus:
            try:
                milvus_id = self._sync_to_milvus(memory_id, user_id, content, memory_type)
                # 更新 milvus_id
                self.update(
                    {'memory_id': memory_id},
                    {'milvus_id': milvus_id}
                )
                logger.info(f"已同步到 Milvus: {milvus_id}")
            except Exception as e:
                logger.error(f"同步到 Milvus 失败：{e}")
        
        return {
            'memory_id': memory_id,
            'milvus_id': milvus_id,
            'memory_type': memory_type,
            'content': content
        }
    
    def search_memories(self, user_id: str, query: str, 
                        memory_type: str = None,
                        category: str = None,
                        top_k: int = 5) -> List[Dict[str, Any]]:
        """
        搜索长期记忆
        
        Args:
            user_id: 用户 ID (UUID 字符串)
            query: 搜索查询
            memory_type: 记忆类型过滤
            category: 分类过滤
            top_k: 返回数量
            
        Returns:
            List[Dict]: 记忆列表
        """
        results = []
        
        # 1. 使用 Milvus 向量搜索（如果可用）
        if self.milvus:
            try:
                milvus_results = self.milvus.search(
                    collection_name='long_term_memory',
                    query=query,
                    filter_expr=f"user_id = '{user_id}'",
                    top_k=top_k,
                    output_fields=['memory_id', 'memory_type', 'importance_score']
                )
                
                # 2. 从 MySQL 获取详细信息
                for hit in milvus_results:
                    memory_id = hit['memory_id']
                    memory = self.find_one({'memory_id': memory_id}, exclude_deleted=False)
                    if memory:
                        memory['score'] = hit['score']
                        results.append(memory)
                        
            except Exception as e:
                logger.error(f"Milvus 搜索失败：{e}")
                # 降级到 MySQL 搜索
        
        # 3. 降级到 MySQL 全文搜索
        if not results:
            conditions = {'user_id': user_id, 'is_active': True}
            if memory_type:
                conditions['memory_type'] = memory_type
            if category:
                conditions['category'] = category
            
            memories = self.find_by(
                conditions,
                fields='*',
                order_by='importance_score DESC',
                limit=top_k,
                exclude_deleted=False
            )
            results = memories
        
        return results[:top_k]
    
    def update_memory(self, memory_id: str, **kwargs) -> int:
        """
        更新长期记忆
        
        Args:
            memory_id: 记忆 ID (UUID 字符串)
            **kwargs: 要更新的字段
            
        Returns:
            int: 影响的行数
        """
        # 1. 更新 MySQL
        rows = self.update({'memory_id': memory_id}, kwargs)
        
        # 2. 同步到 Milvus
        if self.milvus and 'content' in kwargs:
            try:
                milvus_memory = self.find_one({'memory_id': memory_id}, exclude_deleted=False)
                if milvus_memory and milvus_memory.get('milvus_id'):
                    self.milvus.update(
                        collection_name='long_term_memory',
                        milvus_id=milvus_memory['milvus_id'],
                        content=kwargs['content']
                    )
            except Exception as e:
                logger.error(f"更新 Milvus 失败：{e}")
        
        return rows
    
    def delete_memory(self, memory_id: str) -> int:
        """
        删除长期记忆（软删除）
        
        Args:
            memory_id: 记忆 ID (UUID 字符串)
            
        Returns:
            int: 影响的行数
        """
        # 1. MySQL 软删除
        rows = self.soft_delete({'memory_id': memory_id})
        
        # 2. Milvus 删除
        if self.milvus:
            try:
                memory = self.find_one({'memory_id': memory_id}, exclude_deleted=False)
                if memory and memory.get('milvus_id'):
                    self.milvus.delete(
                        collection_name='long_term_memory',
                        milvus_id=memory['milvus_id']
                    )
            except Exception as e:
                logger.error(f"删除 Milvus 失败：{e}")
        
        return rows
    
    def get_memories_by_type(self, user_id: str, memory_type: str,
                             limit: int = 100) -> List[Dict[str, Any]]:
        """
        按类型获取长期记忆
        
        Args:
            user_id: 用户 ID (UUID 字符串)
            memory_type: 记忆类型
            limit: 限制数量
            
        Returns:
            List[Dict]: 记忆列表
        """
        return self.find_by(
            {'user_id': user_id, 'memory_type': memory_type, 'is_active': True},
            order_by='importance_score DESC, created_at DESC',
            limit=limit,
            exclude_deleted=False
        )
    
    def get_memories_by_category(self, user_id: str, category: str,
                                  limit: int = 100) -> List[Dict[str, Any]]:
        """
        按分类获取长期记忆
        
        Args:
            user_id: 用户 ID (UUID 字符串)
            category: 分类
            limit: 限制数量
            
        Returns:
            List[Dict]: 记忆列表
        """
        return self.find_by(
            {'user_id': user_id, 'category': category, 'is_active': True},
            order_by='importance_score DESC, created_at DESC',
            limit=limit,
            exclude_deleted=False
        )
    
    def increment_access_count(self, memory_id: str) -> int:
        """
        增加访问计数
        
        Args:
            memory_id: 记忆 ID (UUID 字符串)
            
        Returns:
            int: 影响的行数
        """
        return self.execute(
            "UPDATE long_term_memory SET access_count = access_count + 1, "
            "last_accessed_at = CURRENT_TIMESTAMP WHERE memory_id = %s",
            (memory_id,)
        )
    
    def _sync_to_milvus(self, memory_id: str, user_id: str, 
                        content: str, memory_type: str) -> str:
        """
        同步到 Milvus
        
        Args:
            memory_id: 记忆 ID (UUID 字符串)
            user_id: 用户 ID (UUID 字符串)
            content: 记忆内容
            memory_type: 记忆类型
            
        Returns:
            str: Milvus 中的 ID (UUID 字符串)
        """
        # 使用 memory_id 作为 Milvus ID
        milvus_id = memory_id
        
        # 准备数据
        data = [{
            'id': milvus_id,
            'user_id': user_id,
            'memory_type': memory_type,
            'content': content,
            'embedding': self._generate_embedding(content)
        }]
        
        # 插入 Milvus
        self.milvus.insert('long_term_memory', data)
        
        return milvus_id
    
    def _generate_embedding(self, text: str) -> List[float]:
        """
        生成 embedding（这里应该调用实际的 embedding 模型）
        
        Args:
            text: 文本内容
            
        Returns:
            List[float]: embedding 向量
        """
        # TODO: 替换为实际的 embedding 调用
        # 这里返回一个 dummy vector
        return [0.0] * 1536
