# -*- coding: utf-8 -*-
"""
记忆剧集 Repository
"""

from typing import Optional, Dict, Any, List
import logging
import uuid
import json

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class MemoryEpisodeRepository(BaseRepository):

    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'memory_episode'

    def create_episode(self, user_id: str, title: str, content: str,
                       entity_id: str = None, episode_type: str = 'interview',
                       fragment_ids: List[str] = None,
                       importance_score: float = 0.5) -> Dict[str, Any]:
        episode_id = str(uuid.uuid4())
        data = {
            'episode_id': episode_id, 'user_id': user_id, 'entity_id': entity_id,
            'title': title, 'content': content, 'episode_type': episode_type,
            'fragment_ids': json.dumps(fragment_ids) if fragment_ids else None,
            'importance_score': importance_score, 'lifecycle_status': 'active',
        }
        self.insert(data)
        return self.get_by_id(episode_id)

    def get_by_id(self, episode_id: str) -> Optional[Dict[str, Any]]:
        return self.find_one({'episode_id': episode_id})

    def get_user_episodes(self, user_id: str, entity_id: str = None,
                          episode_type: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        conditions = {'user_id': user_id}
        if entity_id:
            conditions['entity_id'] = entity_id
        if episode_type:
            conditions['episode_type'] = episode_type
        return self.find_by(conditions, order_by='created_at DESC', limit=limit)

    def get_entity_episodes(self, entity_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self.find_by({'entity_id': entity_id}, order_by='created_at DESC', limit=limit)

    def search_episodes(self, user_id: str, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        sql = """SELECT * FROM memory_episode
                 WHERE user_id = %s AND (title LIKE %s OR content LIKE %s)
                 ORDER BY importance_score DESC LIMIT %s"""
        p = f'%{keyword}%'
        return self.fetch_all(sql, (user_id, p, p, limit))

    def update_lifecycle_status(self, episode_id: str, status: str) -> int:
        return self.update({'episode_id': episode_id}, {'lifecycle_status': status})

    def get_episodes_for_lifecycle_transition(self, user_id: str,
                                              current_status: str,
                                              months_threshold: int) -> List[Dict[str, Any]]:
        sql = """SELECT * FROM memory_episode
                 WHERE user_id = %s AND lifecycle_status = %s
                 AND created_at < DATE_SUB(NOW(), INTERVAL %s MONTH)"""
        return self.fetch_all(sql, (user_id, current_status, months_threshold))

    def get_episode_stats(self, user_id: str) -> Dict[str, Any]:
        sql = """SELECT COUNT(*) as total_count,
                 SUM(CASE WHEN lifecycle_status='active' THEN 1 ELSE 0 END) as active_count,
                 AVG(importance_score) as avg_importance
                 FROM memory_episode WHERE user_id = %s"""
        result = self.fetch_one(sql, (user_id,))
        return result or {}
