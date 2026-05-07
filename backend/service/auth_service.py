# -*- coding: utf-8 -*-
"""
认证服务
提供 JWT token 生成、验证和用户注册登录功能
"""

import logging
import os
import sys
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import bcrypt
import jwt

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grand_parent_dir)

from database.mysql.repository.user_repository import UserRepository
from database.mysql.mysql_client import get_db_client

logger = logging.getLogger(__name__)


class AuthService:
    """认证服务"""
    
    def __init__(self):
        """初始化认证服务"""
        self.db_client = get_db_client()
        self.user_repo = UserRepository(self.db_client)
        
        # JWT 配置
        self.jwt_secret = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
        self.jwt_algorithm = "HS256"
        self.token_expire_hours = int(os.getenv("JWT_EXPIRE_HOURS", "72"))  # 默认 72 小时
    
    def register(self, username: str, password: str, email: str = None, 
                 display_name: str = None) -> Dict[str, Any]:
        """
        用户注册
        
        Args:
            username: 用户名
            password: 明文密码
            email: 邮箱（可选）
            display_name: 显示名称（可选）
        
        Returns:
            Dict: 注册结果
        """
        try:
            # 检查用户名是否已存在
            existing_user = self.user_repo.get_by_username(username)
            if existing_user:
                return {
                    "success": False,
                    "error": "用户名已存在"
                }
            
            # 检查邮箱是否已存在
            if email:
                existing_email = self.user_repo.get_by_email(email)
                if existing_email:
                    return {
                        "success": False,
                        "error": "邮箱已被注册"
                    }
            
            # 加密密码
            password_hash = self._hash_password(password)
            
            # 创建用户
            user = self.user_repo.create_user(
                username=username,
                password_hash=password_hash,
                email=email,
                display_name=display_name or username
            )
            
            if not user:
                return {
                    "success": False,
                    "error": "创建用户失败"
                }
            
            # 生成 token
            token = self._generate_token(user['user_id'])
            
            logger.info(f"用户注册成功：{username}, user_id: {user['user_id']}")
            
            return {
                "success": True,
                "user_id": user['user_id'],
                "username": username,
                "display_name": user.get('display_name'),
                "token": token
            }
            
        except Exception as e:
            logger.error(f"用户注册失败：{e}", exc_info=True)
            return {
                "success": False,
                "error": f"注册失败：{str(e)}"
            }
    
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        用户登录
        
        Args:
            username: 用户名
            password: 明文密码
        
        Returns:
            Dict: 登录结果
        """
        try:
            # 查找用户
            user = self.user_repo.get_by_username(username)
            if not user:
                return {
                    "success": False,
                    "error": "用户名或密码错误"
                }
            
            # 检查用户状态
            if user.get('status') != 1:
                return {
                    "success": False,
                    "error": "账户已被禁用"
                }
            
            # 验证密码
            if not self._verify_password(password, user['password_hash']):
                return {
                    "success": False,
                    "error": "用户名或密码错误"
                }
            
            # 更新最后登录时间
            self.user_repo.update_last_login(user['user_id'])
            
            # 生成 token
            token = self._generate_token(user['user_id'])
            
            logger.info(f"用户登录成功：{username}, user_id: {user['user_id']}")
            
            return {
                "success": True,
                "user_id": user['user_id'],
                "username": user['username'],
                "display_name": user.get('display_name'),
                "email": user.get('email'),
                "token": token,
                "token_type": "Bearer"
            }
            
        except Exception as e:
            logger.error(f"用户登录失败：{e}", exc_info=True)
            return {
                "success": False,
                "error": f"登录失败：{str(e)}"
            }
    
    def verify_token(self, token: str) -> Optional[str]:
        """
        验证 JWT token
        
        Args:
            token: JWT token（不含 Bearer 前缀）
        
        Returns:
            str: user_id（验证成功）或 None（验证失败）
        """
        try:
            payload = jwt.decode(
                token, 
                self.jwt_secret, 
                algorithms=[self.jwt_algorithm]
            )
            return payload.get('user_id')
        except jwt.ExpiredSignatureError:
            logger.warning("Token 已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token 验证失败：{e}")
            return None
    
    def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        """
        获取当前登录用户信息
        
        Args:
            token: JWT token（不含 Bearer 前缀）
        
        Returns:
            Dict: 用户信息或 None
        """
        user_id = self.verify_token(token)
        if not user_id:
            return None
        
        user = self.user_repo.get_by_id(user_id)
        return user
    
    def _hash_password(self, password: str) -> str:
        """密码加密"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """验证密码"""
        return bcrypt.checkpw(
            password.encode('utf-8'), 
            password_hash.encode('utf-8')
        )
    
    def _generate_token(self, user_id: str) -> str:
        """生成 JWT token"""
        now = datetime.utcnow()
        expire = now + timedelta(hours=self.token_expire_hours)
        
        payload = {
            'user_id': user_id,
            'exp': expire,
            'iat': now,
            'type': 'access'
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token


# 单例模式
_auth_service_instance = None


def get_auth_service() -> AuthService:
    """获取认证服务单例"""
    global _auth_service_instance
    if _auth_service_instance is None:
        _auth_service_instance = AuthService()
    return _auth_service_instance
