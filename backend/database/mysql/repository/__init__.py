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

# Memory Constellations 记忆系统 Repositories
from .memory_fragment_repository import MemoryFragmentRepository
from .memory_entity_repository import MemoryEntityRepository
from .memory_episode_repository import MemoryEpisodeRepository
from .memory_saga_repository import MemorySagaRepository
from .cognitive_model_repository import CognitiveModelRepository
from .memory_correction_repository import MemoryCorrectionRepository

__all__ = [
    'BaseRepository',
    'SoftDeleteMixin',
    'UserRepository',
    'SessionRepository',
    'MessageRepository',
    'KnowledgeBaseRepository',
    'DocumentRepository',
    'ChunkRepository',
    'MemoryFragmentRepository',
    'MemoryEntityRepository',
    'MemoryEpisodeRepository',
    'MemorySagaRepository',
    'CognitiveModelRepository',
    'MemoryCorrectionRepository',
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
        # Memory Constellations
        'memory_fragment': MemoryFragmentRepository(db_client),
        'memory_entity': MemoryEntityRepository(db_client),
        'memory_episode': MemoryEpisodeRepository(db_client),
        'memory_saga': MemorySagaRepository(db_client),
        'cognitive_model': CognitiveModelRepository(db_client),
        'memory_correction': MemoryCorrectionRepository(db_client),
    }
