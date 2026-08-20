# -*- coding: utf-8 -*-
"""
CognitiveModelService - 认知画像管理
"""

import logging
import json
import re
from typing import List, Dict, Any

from dashscope import Generation

from .prompts import COGNITIVE_UPDATE_SYSTEM, COGNITIVE_UPDATE_USER
from .config import MemoryConfig

logger = logging.getLogger(__name__)


class CognitiveModelService:
    """认知画像管理服务"""

    DIMENSIONS = {
        'tech_skill': '技术掌握程度',
        'interview_confidence': '面试信心',
        'weakness': '薄弱环节',
        'strength': '优势领域',
        'preparation_level': '准备程度',
        'communication': '表达能力',
    }

    def __init__(self, db_client, api_key: str, llm_model: str = None):
        from database.mysql.repository.cognitive_model_repository import CognitiveModelRepository
        self.cognitive_repo = CognitiveModelRepository(db_client)
        self.api_key = api_key or MemoryConfig.DASHSCOPE_API_KEY
        self.llm_model = llm_model or MemoryConfig.MEMORY_LLM_MODEL

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        return self.cognitive_repo.get_profile_summary(user_id)

    def update_state(self, user_id: str, dimension: str, dimension_key: str,
                     current_value: str, confidence: float = 0.5,
                     ttl_days: int = None) -> Dict[str, Any]:
        if ttl_days is None:
            ttl_days = MemoryConfig.COGNITIVE_MODEL_DEFAULT_TTL_DAYS
        return self.cognitive_repo.upsert_state(
            user_id, dimension, dimension_key, current_value, confidence, ttl_days
        )

    def update_from_conversation(self, user_id: str, conversation_text: str) -> List[Dict[str, Any]]:
        """根据面试对话更新候选人画像"""
        current_profile = self.get_user_profile(user_id)
        current_text = json.dumps(current_profile, ensure_ascii=False) if current_profile else "{}"

        messages = [
            {"role": "system", "content": COGNITIVE_UPDATE_SYSTEM},
            {"role": "user", "content": COGNITIVE_UPDATE_USER.format(
                current_profile=current_text, new_evidence=conversation_text[:2000],
            )},
        ]
        try:
            from service.llm_client import llm_call
            from config.settings import Settings
            cfg = Settings().get_llm_config("memory", model=self.llm_model)
            result = llm_call(messages=messages, model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"] or self.api_key, base_url=cfg["base_url"])
            if result["status_code"] != 200:
                return []
            content = result["content"].strip()
            updates = self._parse_updates(content)
            results = []
            for update in updates:
                dim = update.get('dimension', '')
                if dim not in self.DIMENSIONS:
                    continue
                entry = self.update_state(
                    user_id=user_id, dimension=dim,
                    dimension_key=update.get('dimension_key', dim),
                    current_value=update.get('current_value', ''),
                    confidence=update.get('confidence', 0.5),
                    ttl_days=update.get('ttl_days', 90),
                )
                results.append(entry)
            if results:
                logger.info(f"[CognitiveModel] 更新 {len(results)} 条认知状态")
            return results
        except Exception as e:
            logger.error(f"[CognitiveModel] 更新失败: {e}")
            return []

    def format_for_prompt(self, user_id: str) -> str:
        """格式化认知画像为 prompt 注入文本"""
        profile = self.get_user_profile(user_id)
        if not profile:
            return ""
        lines = ["【候选人画像】"]
        for dim, entries in profile.items():
            dim_name = self.DIMENSIONS.get(dim, dim)
            for entry in entries[:2]:
                conf = entry.get('confidence', 0.5)
                lines.append(f"- {dim_name}/{entry['key']}: {entry['value']} (置信度:{conf:.1f})")
        return "\n".join(lines)

    def _parse_updates(self, content: str) -> List[Dict[str, Any]]:
        try:
            data = json.loads(content)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            match = re.search(r'\[[\s\S]*\]', content)
            if match:
                try:
                    data = json.loads(match.group())
                    return data if isinstance(data, list) else []
                except json.JSONDecodeError:
                    pass
            return []
