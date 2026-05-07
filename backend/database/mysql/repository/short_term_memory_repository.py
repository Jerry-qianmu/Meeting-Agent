# -*- coding: utf-8 -*-
"""
短期记忆 Repository
负责短期记忆的增删改查
"""

from typing import Optional, Dict, Any, List
import logging
import sys
import os
import uuid
import json

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grand_parent_dir)

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ShortTermMemoryRepository(BaseRepository):
    """短期记忆表 Repository"""
    
    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'short_term_memory'
    
    # ==================== 记忆创建 ====================
    
    def create_memory(self, session_id: str, user_id: str,
                     query_summary: str = None,
                     answer_summary: str = None,
                     entities: Dict = None,
                     key_facts: List[Dict] = None,
                     message_id: str = None,
                     base_relevance_score: float = 1.0) -> Dict[str, Any]:
        """
        创建短期记忆
        
        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            query_summary: 问题摘要
            answer_summary: 答案摘要
            entities: 提取的实体 {"person": [...], "organization": [...]}
            key_facts: 关键事实列表 [{"fact": "...", "type": "..."}]
            message_id: 关联的消息 ID
            base_relevance_score: 基础相关性分数 (0-1)
            
        Returns:
            Dict: 创建的记忆数据
        """
        memory_id = str(uuid.uuid4())
        
        data = {
            'memory_id': memory_id,
            'session_uuid': session_id,
            'user_id': user_id,
            'query_summary': query_summary,
            'answer_summary': answer_summary,
            'entities': json.dumps(entities) if entities else None,
            'key_facts': json.dumps(key_facts) if key_facts else None,
            'message_uuid': message_id,
            'base_relevance_score': base_relevance_score,
            'access_count': 1
        }
        
        self.insert(data)
        logger.info(f"创建短期记忆成功：memory_id={memory_id}")
        
        return self.get_by_id(memory_id)
    
    # ==================== 记忆查询 ====================
    
    def get_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """根据 memory_id 获取记忆"""
        return self.find_one({'memory_id': memory_id})
    
    def get_session_memories(self, session_id: str, 
                             limit: int = 50,
                             order_by: str = 'created_at DESC') -> List[Dict[str, Any]]:
        """
        获取会话的短期记忆
        
        Args:
            session_id: 会话 ID
            limit: 限制数量
            order_by: 排序方式
            
        Returns:
            List[Dict]: 记忆列表
        """
        return self.find_by(
            {'session_uuid': session_id},
            order_by=order_by,
            limit=limit
        )
    
    def get_user_memories(self, user_id: str,
                         limit: int = 100,
                         min_relevance: float = 0.5) -> List[Dict[str, Any]]:
        """
        获取用户的短期记忆（按相关性排序）
        
        Args:
            user_id: 用户 ID
            limit: 限制数量
            min_relevance: 最小相关性分数
            
        Returns:
            List[Dict]: 记忆列表
        """
        sql = """
            SELECT * FROM short_term_memory
            WHERE user_id = %s AND base_relevance_score >= %s
            ORDER BY last_accessed_at DESC, base_relevance_score DESC
            LIMIT %s
        """
        return self.fetch_all(sql, (user_id, min_relevance, limit))
    
    def get_recent_memories(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取会话最近的记忆"""
        return self.find_by(
            {'session_uuid': session_id},
            order_by='created_at DESC',
            limit=limit
        )
    
    def search_memories(self, user_id: str, keyword: str,
                       limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索短期记忆（基于 query_summary 和 answer_summary）
        
        Args:
            user_id: 用户 ID
            keyword: 搜索关键词
            limit: 限制数量
            
        Returns:
            List[Dict]: 记忆列表
        """
        sql = """
            SELECT * FROM short_term_memory
            WHERE user_id = %s AND (
                query_summary LIKE %s OR answer_summary LIKE %s
            )
            ORDER BY base_relevance_score DESC, last_accessed_at DESC
            LIMIT %s
        """
        keyword_pattern = f'%{keyword}%'
        return self.fetch_all(sql, (user_id, keyword_pattern, keyword_pattern, limit))
    
    # ==================== 记忆更新 ====================
    
    def increment_access_count(self, memory_id: str) -> int:
        """增加访问次数"""
        return self.execute(
            """UPDATE short_term_memory 
               SET access_count = access_count + 1, 
                   last_accessed_at = CURRENT_TIMESTAMP 
               WHERE memory_id = %s""",
            (memory_id,)
        )
    
    def update_relevance_score(self, memory_id: str, score: float) -> int:
        """更新相关性分数"""
        return self.update(
            {'memory_id': memory_id},
            {'base_relevance_score': score}
        )
    
    def update_entities(self, memory_id: str, entities: Dict) -> int:
        """更新实体信息"""
        return self.update(
            {'memory_id': memory_id},
            {'entities': json.dumps(entities)}
        )
    
    def update_key_facts(self, memory_id: str, key_facts: List[Dict]) -> int:
        """更新关键事实"""
        return self.update(
            {'memory_id': memory_id},
            {'key_facts': json.dumps(key_facts)}
        )
    
    # ==================== 记忆衰减计算 ====================
    
    def calculate_decay_score(self, memory: Dict[str, Any]) -> float:
        """
        计算记忆的实际相关性分数（时间衰减）
        
        公式：current_score = base_relevance * (decay_factor ^ days_passed)
               其中 decay_factor 默认为 0.95（每天衰减 5%）
        
        Args:
            memory: 记忆记录
            
        Returns:
            float: 衰减后的分数
        """
        from datetime import datetime, timedelta
        
        base_score = memory.get('base_relevance_score', 1.0)
        access_count = memory.get('access_count', 1)
        created_at = memory.get('created_at')
        last_accessed = memory.get('last_accessed_at')
        
        if not created_at:
            return base_score
        
        # 转换为 datetime 对象
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        if isinstance(last_accessed, str) and last_accessed:
            last_accessed = datetime.fromisoformat(last_accessed.replace('Z', '+00:00'))
        else:
            last_accessed = created_at
        
        # 计算天数差
        days_passed = (datetime.now() - created_at).days
        days_since_access = (datetime.now() - last_accessed).days
        
        # 时间衰减因子（每天衰减 5%）
        decay_factor = 0.95
        
        # 时间衰减
        time_decay = decay_factor ** days_passed
        
        # 访问奖励（每次访问增加 1% 的分数，上限 1.0）
        access_bonus = min(1.0, 1.0 + (access_count - 1) * 0.01)
        
        # 最近访问奖励（7 天内访问过，乘以 1.2）
        recency_bonus = 1.2 if days_since_access <= 7 else 1.0
        
        # 计算最终分数
        current_score = base_score * time_decay * access_bonus * recency_bonus
        
        return min(1.0, current_score)  # 上限 1.0
    
    def get_decay_scores(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为多个记忆计算衰减分数"""
        for memory in memories:
            memory['current_relevance_score'] = self.calculate_decay_score(memory)
        return memories
    
    # ==================== 统计 ====================
    
    def get_memory_count(self, session_id: str = None, user_id: str = None) -> int:
        """获取记忆数量"""
        conditions = {}
        if session_id:
            conditions['session_uuid'] = session_id
        if user_id:
            conditions['user_id'] = user_id
        return self.count(conditions) if conditions else 0
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """获取会话的短期记忆统计"""
        sql = """
            SELECT 
                COUNT(*) as total_count,
                AVG(base_relevance_score) as avg_relevance,
                SUM(access_count) as total_accesses
            FROM short_term_memory
            WHERE session_uuid = %s
        """
        result = self.fetch_one(sql, (session_id,))
        
        return {
            'total_count': result['total_count'] or 0,
            'avg_relevance': result['avg_relevance'] or 0.0,
            'total_accesses': result['total_accesses'] or 0
        }
