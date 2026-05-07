# -*- coding: utf-8 -*-
"""
User 数据访问层
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


class UserRepository(BaseRepository):
    """用户表 Repository"""
    
    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'user'
    
    def create_user(self, username: str, password_hash: str, email: str = None, 
                    display_name: str = None) -> Dict[str, Any]:
        """
        创建新用户
        
        Args:
            username: 用户名
            password_hash: 加密后的密码
            email: 邮箱（可选）
            display_name: 显示名称（可选）
            
        Returns:
            Dict: 创建的用户数据
        """
        user_id = str(uuid.uuid4())
        data = {
            'user_id': user_id,
            'username': username,
            'password_hash': password_hash,
            'email': email,
            'display_name': display_name,
            'status': 1
        }
        
        self.insert(data)
        logger.info(f"创建用户成功：{username}, user_id: {user_id}")
        
        return self.get_by_username(username)
    
    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """根据 user_id 获取用户"""
        return self.find_one({'user_id': user_id})
    
    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """根据用户名获取用户"""
        return self.find_one({'username': username})
    
    def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """根据邮箱获取用户"""
        return self.find_one({'email': email})
    
    def update_password(self, user_id: str, new_password_hash: str) -> int:
        """更新用户密码"""
        return self.update(
            {'user_id': user_id},
            {'password_hash': new_password_hash}
        )
    
    def update_last_login(self, user_id: str) -> int:
        """更新最后登录时间"""
        sql = """
            UPDATE user 
            SET last_login_at = CURRENT_TIMESTAMP, 
                login_count = login_count + 1 
            WHERE user_id = %s
        """
        return self.execute(sql, (user_id,))
    
    def update_status(self, user_id: str, status: int) -> int:
        """更新用户状态"""
        return self.update(
            {'user_id': user_id},
            {'status': status}
        )
    
    def disable_user(self, user_id: str) -> int:
        """禁用用户"""
        return self.update_status(user_id, 0)
    
    def enable_user(self, user_id: str) -> int:
        """启用用户"""
        return self.update_status(user_id, 1)
    
    def lock_user(self, user_id: str) -> int:
        """锁定用户"""
        return self.update_status(user_id, 2)
    
    def search_users(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索用户（按用户名或邮箱）"""
        sql = """
            SELECT user_id, username, email, display_name, status, created_at
            FROM user
            WHERE username LIKE %s OR email LIKE %s
            ORDER BY created_at DESC
            LIMIT %s
        """
        params = (f'%{keyword}%', f'%{keyword}%', limit)
        return self.fetch_all(sql, params)
    
    def get_user_count(self) -> int:
        """获取用户总数"""
        return self.count()
    
    def get_active_users(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取活跃用户（启用的用户）"""
        return self.find_by(
            {'status': 1},
            fields='*',
            order_by='last_login_at DESC',
            limit=limit
        )
