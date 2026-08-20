# -*- coding: utf-8 -*-
"""
Session 数据访问层
"""

from typing import Optional, Dict, Any, List
import logging
import uuid
import json

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class SessionRepository(BaseRepository):
    """会话表 Repository"""
    
    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'session'
    
    def create_session(self, user_id: str, title: str = None, 
                       knowledge_base_ids: List[str] = None,
                       document_ids: List[str] = None) -> Dict[str, Any]:
        """
        创建新会话
        
        Args:
            user_id: 用户 ID
            title: 会话标题
            knowledge_base_ids: 选中的知识库 ID 列表
            document_ids: 选中的文档 ID 列表
            
        Returns:
            Dict: 创建的会话数据
        """
        session_id = str(uuid.uuid4())
        data = {
            'session_uuid': session_id,
            'user_id': user_id,
            'title': title,
            'status': 1,
            'message_count': 0,
            'token_count': 0,
            'knowledge_base_ids': json.dumps(knowledge_base_ids) if knowledge_base_ids else None,
            'document_ids': json.dumps(document_ids) if document_ids else None
        }
        
        self.insert(data)
        logger.info(f"创建会话成功：user_id={user_id}, session_id={session_id}")
        
        return self.get_by_id(session_id)
    
    def get_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """根据 session_id 获取会话"""
        return self.find_one({'session_uuid': session_id})
    
    def get_user_sessions(self, user_id: str, status: int = 1, 
                          limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取用户的会话列表
        
        Args:
            user_id: 用户 ID
            status: 会话状态（1=进行中，0=归档）
            limit: 每页数量
            offset: 偏移量
            
        Returns:
            List[Dict]: 会话列表
        """
        return self.find_by(
            {'user_id': user_id, 'status': status},
            fields='*',
            order_by='updated_at DESC',
            limit=limit,
            offset=offset
        )
    
    def update_title(self, session_id: str, title: str) -> int:
        """更新会话标题"""
        return self.update(
            {'session_uuid': session_id},
            {'title': title}
        )
    
    def update_summary(self, session_id: str, summary: str) -> int:
        """更新会话摘要"""
        return self.update(
            {'session_uuid': session_id},
            {'summary': summary}
        )
    
    def increment_message_count(self, session_id: str) -> int:
        """增加消息计数"""
        return self.execute(
            "UPDATE session SET message_count = message_count + 1, updated_at = CURRENT_TIMESTAMP WHERE session_uuid = %s",
            (session_id,)
        )
    
    def add_token_count(self, session_id: str, tokens: int) -> int:
        """增加 token 计数"""
        return self.execute(
            "UPDATE session SET token_count = token_count + %s, updated_at = CURRENT_TIMESTAMP WHERE session_uuid = %s",
            (tokens, session_id)
        )
    
    def update_knowledge_bases(self, session_id: str, knowledge_base_ids: List[str]) -> int:
        """更新会话关联的知识库"""
        return self.update(
            {'session_uuid': session_id},
            {'knowledge_base_ids': json.dumps(knowledge_base_ids)}
        )
    
    def update_documents(self, session_id: str, document_ids: List[str]) -> int:
        """更新会话关联的文档"""
        return self.update(
            {'session_uuid': session_id},
            {'document_ids': json.dumps(document_ids)}
        )
    
    def archive_session(self, session_id: str) -> int:
        """归档会话"""
        return self.update(
            {'session_uuid': session_id},
            {'status': 0}
        )
    
    def delete_session(self, session_id: str) -> int:
        """删除会话（硬删除）"""
        return self.execute(
            "DELETE FROM session WHERE session_uuid = %s",
            (session_id,)
        )
    
    def get_session_count(self, user_id: str, status: int = None) -> int:
        """获取会话数量"""
        if status is not None:
            return self.count({'user_id': user_id, 'status': status})
        return self.count({'user_id': user_id})
    
    def get_recent_sessions(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近活跃的会话"""
        return self.find_by(
            {'user_id': user_id, 'status': 1},
            order_by='updated_at DESC',
            limit=limit
        )
