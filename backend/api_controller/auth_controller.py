# -*- coding: utf-8 -*-
"""
认证 API 控制器
提供用户注册、登录、token 验证等接口
"""

import logging
import os
import sys
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grand_parent_dir)

from service.auth_service import get_auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

# HTTP Bearer 认证
security = HTTPBearer(auto_error=False)


# ==================== Request/Response Models ====================

class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=3, max_length=100, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    email: Optional[str] = Field(None, max_length=255, description="邮箱")
    display_name: Optional[str] = Field(None, max_length=100, description="显示名称")


class RegisterResponse(BaseModel):
    """注册响应"""
    success: bool
    user_id: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    token: Optional[str] = None
    error: Optional[str] = None


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class LoginResponse(BaseModel):
    """登录响应"""
    success: bool
    user_id: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    token: Optional[str] = None
    token_type: Optional[str] = None
    error: Optional[str] = None


class UserInfoResponse(BaseModel):
    """用户信息响应"""
    success: bool
    user_id: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    status: Optional[int] = None
    created_at: Optional[str] = None
    error: Optional[str] = None


# ==================== Helper Functions ====================

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    获取当前登录用户
    
    如果 token 无效或过期，返回 None（不抛出异常，由接口自行处理）
    """
    if not credentials:
        return None
    
    token = credentials.credentials
    auth_service = get_auth_service()
    user = auth_service.get_current_user(token)
    
    return user


# ==================== API Endpoints ====================

@router.post("/register", response_model=RegisterResponse, summary="用户注册")
async def register_user(request: RegisterRequest):
    """
    新用户注册
    
    - **username**: 用户名（3-100 字符）
    - **password**: 密码（至少 6 字符）
    - **email**: 邮箱（可选）
    - **display_name**: 显示名称（可选，默认使用用户名）
    
    注册成功后自动登录并返回 token
    """
    try:
        auth_service = get_auth_service()
        result = auth_service.register(
            username=request.username,
            password=request.password,
            email=request.email,
            display_name=request.display_name
        )
        
        return RegisterResponse(**result)
        
    except Exception as e:
        logger.error(f"注册失败：{e}", exc_info=True)
        return RegisterResponse(
            success=False,
            error=f"服务器错误：{str(e)}"
        )


@router.post("/login", response_model=LoginResponse, summary="用户登录")
async def login_user(request: LoginRequest):
    """
    用户登录
    
    - **username**: 用户名
    - **password**: 密码
    
    登录成功后返回 JWT token
    """
    try:
        auth_service = get_auth_service()
        result = auth_service.login(
            username=request.username,
            password=request.password
        )
        
        return LoginResponse(**result)
        
    except Exception as e:
        logger.error(f"登录失败：{e}", exc_info=True)
        return LoginResponse(
            success=False,
            error=f"服务器错误：{str(e)}"
        )


@router.get("/me", response_model=UserInfoResponse, summary="获取当前用户信息")
async def get_current_user_info(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    获取当前登录用户信息
    
    需要在请求头中携带 Bearer Token:
    `Authorization: Bearer <token>`
    """
    if not credentials:
        return UserInfoResponse(
            success=False,
            error="未提供认证 token"
        )
    
    token = credentials.credentials
    auth_service = get_auth_service()
    user = auth_service.get_current_user(token)
    
    if not user:
        return UserInfoResponse(
            success=False,
            error="token 无效或已过期"
        )
    
    return UserInfoResponse(
        success=True,
        user_id=user.get('user_id'),
        username=user.get('username'),
        display_name=user.get('display_name'),
        email=user.get('email'),
        avatar_url=user.get('avatar_url'),
        status=user.get('status'),
        created_at=user.get('created_at')
    )


@router.post("/verify", summary="验证 token 有效性")
async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    验证当前 token 是否有效
    
    返回当前用户 ID（如果有效）
    """
    if not credentials:
        return {
            "valid": False,
            "user_id": None,
            "error": "未提供认证 token"
        }
    
    token = credentials.credentials
    auth_service = get_auth_service()
    user_id = auth_service.verify_token(token)
    
    if not user_id:
        return {
            "valid": False,
            "user_id": None,
            "error": "token 无效或已过期"
        }
    
    return {
        "valid": True,
        "user_id": user_id
    }
