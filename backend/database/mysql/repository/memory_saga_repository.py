# -*- coding: utf-8 -*-
"""
记忆传奇 Repository
"""

from typing import Optional, Dict, Any, List
import logging
import uuid
import json

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class MemorySagaRepository(BaseRepository):

    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'memory_saga'

    def create_saga(self, user_id: str, title: str, summary: str,
                    saga_type: str = 'career', entity_ids: List[str] = None,
                    episode_ids: List[str] = None, emotion_axes: dict = None,
                    importance_score: float = 0.7) -> Dict[str, Any]:
        saga_id = str(uuid.uuid4())
        data = {
            'saga_id': saga_id, 'user_id': user_id, 'title': title,
            'summary': summary, 'saga_type': saga_type,
            'entity_ids': json.dumps(entity_ids) if entity_ids else None,
            'episode_ids': json.dumps(episode_ids) if episode_ids else None,
            'emotion_axes': json.dumps(emotion_axes) if emotion_axes else None,
            'importance_score': importance_score,
        }
        self.insert(data)
        return self.get_by_id(saga_id)

    def get_by_id(self, saga_id: str) -> Optional[Dict[str, Any]]:
        return self.find_one({'saga_id': saga_id})

    def get_user_sagas(self, user_id: str, saga_type: str = None,
                       limit: int = 20) -> List[Dict[str, Any]]:
        conditions = {'user_id': user_id}
        if saga_type:
            conditions['saga_type'] = saga_type
        return self.find_by(conditions, order_by='importance_score DESC', limit=limit)

    def update_saga(self, saga_id: str, **kwargs) -> int:
        return self.update({'saga_id': saga_id}, kwargs)

    def get_saga_stats(self, user_id: str) -> Dict[str, Any]:
        sql = """SELECT COUNT(*) as total_count,
                 AVG(importance_score) as avg_importance
                 FROM memory_saga WHERE user_id = %s"""
        result = self.fetch_one(sql, (user_id,))
        return result or {}
