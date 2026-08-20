# -*- coding: utf-8 -*-
"""
OSS 服务包
提供阿里云 OSS 文件存储功能
"""

from .oss_service import OSSService, get_oss_service

__all__ = [
    'OSSService',
    'get_oss_service',
]
