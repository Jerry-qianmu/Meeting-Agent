# -*- coding: utf-8 -*-
"""
Repository 层包
提供数据访问接口，实现业务逻辑与数据持久化的解耦

重要说明：
- 所有 ID 统一使用 CHAR(36) UUID 字符串格式
- 生成方式：str(uuid.uuid4())
- 不要使用 bytes 或 hex 格式
"""

from .base_repository import BaseRepository
from .soft_delete_mixin import SoftDeleteMixin
from .user_repository import UserRepository
from .session_repository import SessionRepository
from .message_repository import MessageRepository
from .knowledge_base_repository import KnowledgeBaseRepository
from .document_repository import DocumentRepository
from .chunk_repository import ChunkRepository
from .short_term_memory_repository import ShortTermMemoryRepository
from .long_term_memory_repository import LongTermMemoryRepository

__all__ = [
    'BaseRepository',
    'SoftDeleteMixin',
    'UserRepository',
    'SessionRepository',
    'MessageRepository',
    'KnowledgeBaseRepository',
    'DocumentRepository',
    'ChunkRepository',
    'ShortTermMemoryRepository',
    'LongTermMemoryRepository',
]


def get_repositories(db_client, milvus_client=None):
    """
    获取所有 repository 实例
    
    Args:
        db_client: MysqlClient 实例
        milvus_client: MilvusClient 实例（可选，用于长期记忆）
        
    Returns:
        dict: {repository_name: repository_instance}
    """
    return {
        'user': UserRepository(db_client),
        'session': SessionRepository(db_client),
        'message': MessageRepository(db_client),
        'knowledge_base': KnowledgeBaseRepository(db_client),
        'document': DocumentRepository(db_client),
        'chunk': ChunkRepository(db_client),
        'short_term_memory': ShortTermMemoryRepository(db_client),
        'long_term_memory': LongTermMemoryRepository(db_client, milvus_client),
    }
