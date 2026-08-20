# -*- coding: utf-8 -*-
"""
记忆修正 Repository
"""

from typing import Optional, Dict, Any, List
import logging
import uuid

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class MemoryCorrectionRepository(BaseRepository):

    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'memory_correction'

    def create_correction(self, user_id: str, corrected_content: str,
                          correction_type: str = 'new_correction',
                          original_fragment_id: str = None,
                          original_content: str = None,
                          reason: str = None) -> Dict[str, Any]:
        correction_id = str(uuid.uuid4())
        data = {
            'correction_id': correction_id, 'user_id': user_id,
            'original_fragment_id': original_fragment_id,
            'original_content': original_content,
            'corrected_content': corrected_content,
            'correction_type': correction_type, 'reason': reason,
        }
        self.insert(data)
        return self.get_by_id(correction_id)

    def get_by_id(self, correction_id: str) -> Optional[Dict[str, Any]]:
        return self.find_one({'correction_id': correction_id})

    def get_user_corrections(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.find_by({'user_id': user_id}, order_by='created_at DESC', limit=limit)

    def get_corrections_for_fragment(self, fragment_id: str) -> List[Dict[str, Any]]:
        return self.find_by({'original_fragment_id': fragment_id}, order_by='created_at DESC')
