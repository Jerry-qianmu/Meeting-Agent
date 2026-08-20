# -*- coding: utf-8 -*-
"""
Message 数据访问层
"""

from typing import Optional, Dict, Any, List
import logging
import uuid
import json

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class MessageRepository(BaseRepository):
    """消息表 Repository"""
    
    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'message'
    
    # ==================== 消息创建 ====================
    
    def create_user_message(self, session_id: str, user_id: str, 
                           content: str, parent_id: str = None) -> Dict[str, Any]:
        """
        创建用户消息
        
        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            content: 消息内容
            parent_id: 父消息 ID
            
        Returns:
            Dict: 创建的消息数据
        """
        message_id = str(uuid.uuid4())
        data = {
            'message_uuid': message_id,
            'session_uuid': session_id,
            'user_id': user_id,
            'role': 0,  # user
            'content': content,
            'parent_message_id': parent_id,
            'status': 1
        }
        
        self.insert(data)
        logger.info(f"创建用户消息成功：session_id={session_id}")
        
        return self.get_by_id(message_id)
    
    def create_assistant_message(self, session_id: str, user_id: str,
                                  content: str, model: str = None,
                                  tokens_prompt: int = None,
                                  tokens_completion: int = None,
                                  latency_ms: int = None,
                                  parent_id: str = None) -> Dict[str, Any]:
        """
        创建助手消息
        
        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            content: 消息内容
            model: 使用的模型
            tokens_prompt: prompt token 数
            tokens_completion: completion token 数
            latency_ms: 响应耗时
            parent_id: 父消息 ID
            
        Returns:
            Dict: 创建的消息数据
        """
        message_id = str(uuid.uuid4())
        tokens_total = (tokens_prompt or 0) + (tokens_completion or 0)
        
        data = {
            'message_uuid': message_id,
            'session_uuid': session_id,
            'user_id': user_id,
            'role': 1,  # assistant
            'content': content,
            'parent_message_id': parent_id,
            'model_used': model,
            'tokens_prompt': tokens_prompt,
            'tokens_completion': tokens_completion,
            'tokens_total': tokens_total,
            'latency_ms': latency_ms,
            'status': 1
        }
        
        self.insert(data)
        logger.info(f"创建助手消息成功：session_id={session_id}, tokens={tokens_total}")
        
        return self.get_by_id(message_id)
    
    def create_system_message(self, session_id: str, user_id: str,
                               content: str) -> Dict[str, Any]:
        """创建系统消息"""
        message_id = str(uuid.uuid4())
        data = {
            'message_uuid': message_id,
            'session_uuid': session_id,
            'user_id': user_id,
            'role': 2,  # system
            'content': content,
            'status': 1
        }
        
        self.insert(data)
        return self.get_by_id(message_id)
    
    def create_tool_message(self, session_id: str, user_id: str,
                            content: str, tool_calls: dict = None) -> Dict[str, Any]:
        """创建工具消息"""
        message_id = str(uuid.uuid4())
        data = {
            'message_uuid': message_id,
            'session_uuid': session_id,
            'user_id': user_id,
            'role': 3,  # tool
            'content': content,
            'tool_calls': json.dumps(tool_calls) if tool_calls else None,
            'status': 1
        }
        
        self.insert(data)
        return self.get_by_id(message_id)
    
    # ==================== 消息查询 ====================
    
    def get_by_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        """根据 message_id 获取消息"""
        return self.find_one({'message_uuid': message_id})
    
    def get_session_messages(self, session_id: str, 
                             limit: int = None,
                             offset: int = None) -> List[Dict[str, Any]]:
        """
        获取会话的所有消息
        
        Args:
            session_id: 会话 ID
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            List[Dict]: 消息列表
        """
        sql = """
            SELECT * FROM message
            WHERE session_uuid = %s
            ORDER BY created_at ASC
        """
        if limit:
            sql += f" LIMIT {limit}"
            if offset:
                sql += f" OFFSET {offset}"
        
        return self.fetch_all(sql, (session_id,))
    
    def get_messages_by_role(self, session_id: str, role: int,
                              limit: int = None) -> List[Dict[str, Any]]:
        """根据角色获取消息"""
        conditions = {'session_uuid': session_id, 'role': role}
        return self.find_by(
            conditions,
            order_by='created_at ASC',
            limit=limit
        )
    
    def get_user_messages(self, session_id: str, limit: int = None) -> List[Dict[str, Any]]:
        """获取用户消息"""
        return self.get_messages_by_role(session_id, 0, limit)
    
    def get_assistant_messages(self, session_id: str, limit: int = None) -> List[Dict[str, Any]]:
        """获取助手消息"""
        return self.get_messages_by_role(session_id, 1, limit)
    
    def get_recent_messages(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """获取用户最近的消息"""
        return self.find_by(
            {'user_id': user_id},
            order_by='created_at DESC',
            limit=limit
        )
    
    # ==================== 消息更新 ====================
    
    def update_tool_calls(self, message_id: str, tool_calls: dict) -> int:
        """更新工具调用信息"""
        return self.update(
            {'message_uuid': message_id},
            {'tool_calls': json.dumps(tool_calls)}
        )
    
    def update_token_usage(self, message_id: str, tokens_prompt: int = None,
                           tokens_completion: int = None, latency_ms: int = None) -> int:
        """更新 token 使用情况"""
        data = {}
        if tokens_prompt is not None:
            data['tokens_prompt'] = tokens_prompt
        if tokens_completion is not None:
            data['tokens_completion'] = tokens_completion
        if latency_ms is not None:
            data['latency_ms'] = latency_ms
        
        if data:
            # 计算总 token
            if tokens_prompt is not None and tokens_completion is not None:
                data['tokens_total'] = tokens_prompt + tokens_completion
        
        return self.update({'message_uuid': message_id}, data)
    
    def mark_message_failed(self, message_id: str, error_message: str) -> int:
        """标记消息失败"""
        return self.update(
            {'message_uuid': message_id},
            {'status': 2, 'error_message': error_message}
        )
    
    # ==================== 统计 ====================
    
    def get_message_count(self, session_id: str = None, user_id: str = None) -> int:
        """获取消息数量"""
        conditions = {}
        if session_id:
            conditions['session_uuid'] = session_id
        if user_id:
            conditions['user_id'] = user_id
        return self.count(conditions) if conditions else 0
    
    def get_total_token_usage(self, user_id: str, days: int = None) -> int:
        """获取用户总 token 消耗"""
        sql = "SELECT COALESCE(SUM(tokens_total), 0) as total FROM message WHERE user_id = %s AND role = 1"
        params = [user_id]
        
        if days:
            sql += " AND created_at >= DATE_SUB(CURRENT_DATE, INTERVAL %s DAY)"
            params.append(days)
        
        result = self.fetch_one(sql, tuple(params))
        return result['total'] if result else 0
    
    def delete_messages_by_session(self, session_id: str) -> int:
        """删除会话的所有消息"""
        return self.execute(
            "DELETE FROM message WHERE session_uuid = %s",
            (session_id,)
        )
