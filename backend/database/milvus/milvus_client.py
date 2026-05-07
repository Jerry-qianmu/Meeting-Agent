# -*- coding: utf-8 -*-
"""
Milvus 客户端包装
提供连接管理和健康检查
"""

import logging
import sys
import os

from pymilvus import MilvusClient as PyMilvusClient
logger = logging.getLogger(__name__)

cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.insert(0, os.path.dirname(parent_dir))

from config.settings import Settings
settings = Settings()


class MilvusClient:
    """Milvus 客户端包装类"""
    
    def __init__(self, settings: Settings = None):
        """
        初始化 Milvus 客户端
        
        Args:
            settings: 配置对象，如果为 None 则自动加载
        """
        if settings is None:
            settings = Settings()
        
        self.settings = settings
        
        # 构建连接 URI
        self.uri = f"http://{settings.milvus_host}:{settings.milvus_port}"
        self.token = f"{settings.milvus_user}:{settings.milvus_password}"
        
        # 创建客户端
        try:
            self.client = PyMilvusClient(uri=self.uri, token=self.token)
            logger.info(f"Milvus 客户端初始化成功：{self.uri}")
        except Exception as e:
            logger.error(f"Milvus 客户端初始化失败：{e}")
            raise
    
    def is_connected(self) -> bool:
        """检查连接是否可用"""
        try:
            # 尝试列出 collection（轻量级操作）
            collections = self.client.list_collections()
            logger.debug(f"Milvus 连接正常，共有 {len(collections)} 个 collection")
            return True
        except Exception as e:
            logger.warning(f"Milvus 连接检查失败：{e}")
            return False
    
    def get_client(self) -> PyMilvusClient:
        """获取底层的 MilvusClient 实例"""
        return self.client
    
    def close(self):
        """关闭连接"""
        try:
            # MilvusClient 没有明确的 close 方法，但我们可以释放引用
            if self.client:
                del self.client
                logger.info("Milvus 客户端已关闭")
        except Exception as e:
            logger.warning(f"关闭 Milvus 客户端失败：{e}")


def get_milvus_client(settings: Settings = None) -> MilvusClient:
    """
    获取 Milvus 客户端实例（工厂函数）
    
    Args:
        settings: 配置对象
        
    Returns:
        MilvusClient: Milvus 客户端实例
    """
    return MilvusClient(settings)
