# -*- coding: utf-8 -*-
"""
记忆碎片 Repository
"""

from typing import Optional, Dict, Any, List
import logging
import uuid

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class MemoryFragmentRepository(BaseRepository):
    """记忆碎片表 Repository"""

    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'memory_fragment'

    def create_fragment(self, user_id: str, content: str,
                        fragment_type: str = 'fact',
                        session_uuid: str = None,
                        message_uuid: str = None,
                        entity_id: str = None,
                        importance_score: float = 0.5) -> Dict[str, Any]:
        """创建记忆碎片"""
        fragment_id = str(uuid.uuid4())
        data = {
            'fragment_id': fragment_id,
            'user_id': user_id,
            'session_uuid': session_uuid,
            'message_uuid': message_uuid,
            'content': content,
            'fragment_type': fragment_type,
            'entity_id': entity_id,
            'importance_score': importance_score,
            'access_count': 0,
            'lifecycle_status': 'active',
        }
        self.insert(data)
        logger.info(f"创建记忆碎片：fragment_id={fragment_id}")
        return self.get_by_id(fragment_id)

    def create_fragments_batch(self, fragments: List[Dict[str, Any]]) -> int:
        """批量创建记忆碎片"""
        for f in fragments:
            if 'fragment_id' not in f:
                f['fragment_id'] = str(uuid.uuid4())
            if 'access_count' not in f:
                f['access_count'] = 0
            if 'lifecycle_status' not in f:
                f['lifecycle_status'] = 'active'
            if 'consolidated' not in f:
                f['consolidated'] = False
        count = self.insert_batch(fragments)
        logger.info(f"批量创建记忆碎片：{count} 条")
        return count

    def get_by_id(self, fragment_id: str) -> Optional[Dict[str, Any]]:
        return self.find_one({'fragment_id': fragment_id})

    def get_user_fragments(self, user_id: str, limit: int = 100,
                           fragment_type: str = None,
                           entity_id: str = None,
                           consolidated: bool = None,
                           lifecycle_status: str = None) -> List[Dict[str, Any]]:
        """获取用户的碎片列表"""
        conditions = {'user_id': user_id}
        if fragment_type:
            conditions['fragment_type'] = fragment_type
        if entity_id:
            conditions['entity_id'] = entity_id
        if consolidated is not None:
            conditions['consolidated'] = consolidated
        if lifecycle_status:
            conditions['lifecycle_status'] = lifecycle_status
        return self.find_by(conditions, order_by='created_at DESC', limit=limit)

    def get_unlinked_fragments(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取未链接到实体的碎片"""
        sql = """
            SELECT * FROM memory_fragment
            WHERE user_id = %s AND entity_id IS NULL
            AND consolidated = FALSE AND deleted_at IS NULL
            AND lifecycle_status = 'active'
            ORDER BY importance_score DESC, created_at DESC
            LIMIT %s
        """
        return self.fetch_all(sql, (user_id, limit))

    def get_unconsolidated_fragments(self, user_id: str, entity_id: str,
                                     limit: int = 100) -> List[Dict[str, Any]]:
        """获取指定实体下未整合的碎片"""
        sql = """
            SELECT * FROM memory_fragment
            WHERE user_id = %s AND entity_id = %s
            AND consolidated = FALSE AND deleted_at IS NULL
            AND lifecycle_status = 'active'
            ORDER BY created_at ASC
            LIMIT %s
        """
        return self.fetch_all(sql, (user_id, entity_id, limit))

    def get_session_fragments(self, session_uuid: str) -> List[Dict[str, Any]]:
        return self.find_by({'session_uuid': session_uuid}, order_by='created_at DESC')

    def search_by_keyword(self, user_id: str, keyword: str,
                          limit: int = 20) -> List[Dict[str, Any]]:
        """关键词搜索碎片"""
        sql = """
            SELECT * FROM memory_fragment
            WHERE user_id = %s AND content LIKE %s
            AND deleted_at IS NULL AND lifecycle_status != 'tombstone'
            ORDER BY importance_score DESC, created_at DESC
            LIMIT %s
        """
        return self.fetch_all(sql, (user_id, f'%{keyword}%', limit))

    def link_to_entity(self, fragment_id: str, entity_id: str) -> int:
        return self.update({'fragment_id': fragment_id}, {'entity_id': entity_id})

    def mark_consolidated(self, fragment_id: str) -> int:
        return self.update({'fragment_id': fragment_id}, {'consolidated': True})

    def increment_access(self, fragment_id: str) -> int:
        return self.execute(
            """UPDATE memory_fragment
               SET access_count = access_count + 1,
                   last_accessed_at = CURRENT_TIMESTAMP
               WHERE fragment_id = %s""",
            (fragment_id,)
        )

    def update_lifecycle_status(self, fragment_id: str, status: str) -> int:
        return self.update({'fragment_id': fragment_id}, {'lifecycle_status': status})

    def update_content(self, fragment_id: str, content: str) -> int:
        return self.update({'fragment_id': fragment_id}, {'content': content})

    def get_fragments_for_lifecycle_transition(self, user_id: str,
                                               current_status: str,
                                               days_threshold: int) -> List[Dict[str, Any]]:
        """获取需要生命周期转换的碎片"""
        sql = """
            SELECT * FROM memory_fragment
            WHERE user_id = %s AND lifecycle_status = %s AND deleted_at IS NULL
            AND (
                (last_accessed_at IS NULL AND created_at < DATE_SUB(NOW(), INTERVAL %s DAY))
                OR (last_accessed_at IS NOT NULL AND last_accessed_at < DATE_SUB(NOW(), INTERVAL %s DAY))
            )
        """
        return self.fetch_all(sql, (user_id, current_status, days_threshold, days_threshold))

    def count_by_entity(self, user_id: str, entity_id: str) -> int:
        return self.count({'user_id': user_id, 'entity_id': entity_id})

    def count_unconsolidated(self, user_id: str, entity_id: str) -> int:
        sql = """
            SELECT COUNT(*) as count FROM memory_fragment
            WHERE user_id = %s AND entity_id = %s
            AND consolidated = FALSE AND deleted_at IS NULL
        """
        result = self.fetch_one(sql, (user_id, entity_id))
        return result['count'] if result else 0

    def get_user_fragment_stats(self, user_id: str) -> Dict[str, Any]:
        sql = """
            SELECT
                COUNT(*) as total_count,
                SUM(CASE WHEN lifecycle_status = 'active' THEN 1 ELSE 0 END) as active_count,
                SUM(CASE WHEN consolidated = TRUE THEN 1 ELSE 0 END) as consolidated_count,
                SUM(CASE WHEN entity_id IS NULL THEN 1 ELSE 0 END) as unlinked_count,
                AVG(importance_score) as avg_importance
            FROM memory_fragment
            WHERE user_id = %s AND deleted_at IS NULL
        """
        result = self.fetch_one(sql, (user_id,))
        return result or {}
