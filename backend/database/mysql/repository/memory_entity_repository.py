# -*- coding: utf-8 -*-
"""
记忆实体 Repository
"""

from typing import Optional, Dict, Any, List
import logging
import uuid
import json

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class MemoryEntityRepository(BaseRepository):

    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'memory_entity'

    def create_entity(self, user_id: str, name: str, entity_type: str,
                      description: str = None, importance_score: float = 0.5,
                      status: str = 'seed', metadata: dict = None) -> Dict[str, Any]:
        entity_id = str(uuid.uuid4())
        data = {
            'entity_id': entity_id, 'user_id': user_id, 'name': name,
            'entity_type': entity_type, 'description': description,
            'importance_score': importance_score, 'status': status,
            'metadata': json.dumps(metadata) if metadata else None,
            'fragment_count': 0, 'episode_count': 0,
        }
        self.insert(data)
        return self.get_by_id(entity_id)

    def get_by_id(self, entity_id: str) -> Optional[Dict[str, Any]]:
        return self.find_one({'entity_id': entity_id})

    def get_by_name_and_type(self, user_id: str, name: str,
                             entity_type: str) -> Optional[Dict[str, Any]]:
        return self.find_one({'user_id': user_id, 'name': name, 'entity_type': entity_type})

    def get_user_entities(self, user_id: str, entity_type: str = None,
                          status: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        conditions = {'user_id': user_id}
        if entity_type:
            conditions['entity_type'] = entity_type
        if status:
            conditions['status'] = status
        return self.find_by(conditions, order_by='importance_score DESC', limit=limit)

    def get_all_entity_names(self, user_id: str) -> List[Dict[str, Any]]:
        sql = """SELECT entity_id, name, entity_type, description, status
                 FROM memory_entity WHERE user_id = %s AND deleted_at IS NULL
                 ORDER BY importance_score DESC"""
        return self.fetch_all(sql, (user_id,))

    def search_entities(self, user_id: str, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        sql = """SELECT * FROM memory_entity
                 WHERE user_id = %s AND (name LIKE %s OR description LIKE %s)
                 AND deleted_at IS NULL ORDER BY importance_score DESC LIMIT %s"""
        p = f'%{keyword}%'
        return self.fetch_all(sql, (user_id, p, p, limit))

    def update_fragment_count(self, entity_id: str, delta: int = 1) -> int:
        return self.execute(
            "UPDATE memory_entity SET fragment_count = fragment_count + %s WHERE entity_id = %s",
            (delta, entity_id))

    def update_episode_count(self, entity_id: str, delta: int = 1) -> int:
        return self.execute(
            "UPDATE memory_entity SET episode_count = episode_count + %s WHERE entity_id = %s",
            (delta, entity_id))

    def update_status(self, entity_id: str, status: str) -> int:
        return self.update({'entity_id': entity_id}, {'status': status})

    def update_description(self, entity_id: str, description: str) -> int:
        return self.update({'entity_id': entity_id}, {'description': description})

    def increment_importance(self, entity_id: str, delta: float = 0.1) -> int:
        return self.execute(
            "UPDATE memory_entity SET importance_score = LEAST(1.0, importance_score + %s) WHERE entity_id = %s",
            (delta, entity_id))

    def get_seed_entities(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.find_by({'user_id': user_id, 'status': 'seed'}, order_by='created_at DESC', limit=limit)

    def find_duplicate_entities(self, user_id: str) -> List[Dict[str, Any]]:
        sql = """SELECT name, entity_type, COUNT(*) as cnt, GROUP_CONCAT(entity_id) as entity_ids
                 FROM memory_entity WHERE user_id = %s AND deleted_at IS NULL
                 GROUP BY name, entity_type HAVING cnt > 1"""
        return self.fetch_all(sql, (user_id,))

    def get_entity_stats(self, user_id: str) -> Dict[str, Any]:
        sql = """SELECT COUNT(*) as total_count,
                 SUM(CASE WHEN status='seed' THEN 1 ELSE 0 END) as seed_count,
                 SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) as active_count,
                 SUM(CASE WHEN status='mature' THEN 1 ELSE 0 END) as mature_count,
                 SUM(fragment_count) as total_fragments, SUM(episode_count) as total_episodes
                 FROM memory_entity WHERE user_id = %s AND deleted_at IS NULL"""
        result = self.fetch_one(sql, (user_id,))
        return result or {}
