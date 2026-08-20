# -*- coding: utf-8 -*-
"""
认知模型 Repository
"""

from typing import Optional, Dict, Any, List
import logging
import uuid
from datetime import datetime, timedelta

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class CognitiveModelRepository(BaseRepository):

    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'cognitive_model'

    def upsert_state(self, user_id: str, dimension: str, dimension_key: str,
                     current_value: str, confidence: float = 0.5,
                     ttl_days: int = 90) -> Dict[str, Any]:
        existing = self.find_one({
            'user_id': user_id, 'dimension': dimension, 'dimension_key': dimension_key
        })
        expires_at = (datetime.now() + timedelta(days=ttl_days)).strftime('%Y-%m-%d %H:%M:%S')

        if existing:
            self.update(
                {'model_id': existing['model_id']},
                {'current_value': current_value, 'confidence': confidence,
                 'evidence_count': existing.get('evidence_count', 0) + 1,
                 'ttl_days': ttl_days, 'expires_at': expires_at}
            )
            return self.get_by_id(existing['model_id'])
        else:
            model_id = str(uuid.uuid4())
            data = {
                'model_id': model_id, 'user_id': user_id,
                'dimension': dimension, 'dimension_key': dimension_key,
                'current_value': current_value, 'confidence': confidence,
                'evidence_count': 1, 'ttl_days': ttl_days, 'expires_at': expires_at,
            }
            self.insert(data)
            return self.get_by_id(model_id)

    def get_by_id(self, model_id: str) -> Optional[Dict[str, Any]]:
        return self.find_one({'model_id': model_id})

    def get_user_states(self, user_id: str, dimension: str = None) -> List[Dict[str, Any]]:
        conditions = {'user_id': user_id}
        if dimension:
            conditions['dimension'] = dimension
        return self.find_by(conditions, order_by='confidence DESC, updated_at DESC')

    def get_active_states(self, user_id: str) -> List[Dict[str, Any]]:
        sql = """SELECT * FROM cognitive_model
                 WHERE user_id = %s AND (expires_at IS NULL OR expires_at > NOW())
                 ORDER BY dimension, confidence DESC"""
        return self.fetch_all(sql, (user_id,))

    def get_expired_states(self, user_id: str) -> List[Dict[str, Any]]:
        sql = """SELECT * FROM cognitive_model
                 WHERE user_id = %s AND expires_at IS NOT NULL AND expires_at <= NOW()"""
        return self.fetch_all(sql, (user_id,))

    def increment_evidence(self, model_id: str) -> int:
        return self.execute(
            "UPDATE cognitive_model SET evidence_count = evidence_count + 1 WHERE model_id = %s",
            (model_id,))

    def delete_expired(self, user_id: str) -> int:
        sql = """DELETE FROM cognitive_model
                 WHERE user_id = %s AND expires_at IS NOT NULL AND expires_at <= NOW()"""
        return self.execute(sql, (user_id,))

    def get_profile_summary(self, user_id: str) -> Dict[str, Any]:
        states = self.get_active_states(user_id)
        profile = {}
        for s in states:
            dim = s['dimension']
            if dim not in profile:
                profile[dim] = []
            profile[dim].append({
                'key': s['dimension_key'], 'value': s['current_value'],
                'confidence': s['confidence'], 'evidence_count': s['evidence_count'],
            })
        return profile
