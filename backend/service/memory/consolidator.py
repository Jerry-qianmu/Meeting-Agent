# -*- coding: utf-8 -*-
"""
Consolidator - 碎片→剧集整合器

将同一实体下的多条记忆碎片整合为连贯的叙事段落（Episode）
"""

import logging
import json
import re
from typing import List, Dict, Any, Optional

from dashscope import Generation

from .prompts import ARCHIVIST_CONSOLIDATE_SYSTEM, ARCHIVIST_CONSOLIDATE_USER
from .config import MemoryConfig

logger = logging.getLogger(__name__)


class Consolidator:
    """碎片→剧集整合器"""

    def __init__(self, db_client, api_key: str, llm_model: str = None,
                 embedding_service=None, milvus_service=None):
        from database.mysql.repository.memory_fragment_repository import MemoryFragmentRepository
        from database.mysql.repository.memory_episode_repository import MemoryEpisodeRepository
        from database.mysql.repository.memory_entity_repository import MemoryEntityRepository

        self.fragment_repo = MemoryFragmentRepository(db_client)
        self.episode_repo = MemoryEpisodeRepository(db_client)
        self.entity_repo = MemoryEntityRepository(db_client)
        self.api_key = api_key or MemoryConfig.DASHSCOPE_API_KEY
        self.llm_model = llm_model or MemoryConfig.MEMORY_LLM_MODEL
        self.embedding_service = embedding_service
        self.milvus_service = milvus_service

    def consolidate_entity(self, user_id: str, entity_id: str,
                           min_fragments: int = 3) -> Optional[Dict[str, Any]]:
        """
        将指定实体下的未整合碎片整合为一个剧集

        Returns:
            创建的剧集，或 None
        """
        fragments = self.fragment_repo.get_unconsolidated_fragments(
            user_id, entity_id, limit=50
        )

        if len(fragments) < min_fragments:
            return None

        entity = self.entity_repo.get_by_id(entity_id)
        if not entity:
            return None

        # LLM 整合
        result = self._call_llm_consolidate(
            entity_name=entity['name'],
            entity_type=entity.get('entity_type', 'concept'),
            fragments=fragments,
        )

        if not result:
            return None

        # 创建剧集
        fragment_ids = [f['fragment_id'] for f in fragments]
        episode = self.episode_repo.create_episode(
            user_id=user_id,
            title=result.get('title', f"{entity['name']}相关记忆"),
            content=result.get('content', ''),
            entity_id=entity_id,
            episode_type=result.get('episode_type', 'interview'),
            fragment_ids=fragment_ids,
            importance_score=result.get('importance_score', 0.5),
        )

        # 标记碎片已整合
        for frag in fragments:
            self.fragment_repo.mark_consolidated(frag['fragment_id'])

        # 更新实体剧集计数
        self.entity_repo.update_episode_count(entity_id, 1)

        logger.info(
            f"[Consolidator] 整合完成: entity={entity['name']}, "
            f"fragments={len(fragments)}→episode={episode['episode_id']}"
        )

        # Milvus 向量索引
        self._index_episode_to_milvus(user_id, episode)

        return episode

    def consolidate_all_entities(self, user_id: str,
                                  min_fragments: int = 3) -> List[Dict[str, Any]]:
        """批量整合所有符合条件的实体"""
        entities = self.entity_repo.get_user_entities(user_id, status='active')
        episodes = []

        for entity in entities:
            unconsolidated_count = self.fragment_repo.count_unconsolidated(
                user_id, entity['entity_id']
            )
            if unconsolidated_count >= min_fragments:
                episode = self.consolidate_entity(
                    user_id, entity['entity_id'], min_fragments
                )
                if episode:
                    episodes.append(episode)

        logger.info(f"[Consolidator] 批量整合: {len(episodes)} 个剧集")
        return episodes

    def _call_llm_consolidate(self, entity_name: str, entity_type: str,
                               fragments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """调用 LLM 整合碎片"""
        fragment_lines = []
        for i, frag in enumerate(fragments, 1):
            created = frag.get('created_at', '')
            if hasattr(created, 'strftime'):
                created = created.strftime('%Y-%m-%d %H:%M')
            fragment_lines.append(f"{i}. [{created}] {frag['content']}")
        fragments_text = '\n'.join(fragment_lines)

        messages = [
            {"role": "system", "content": ARCHIVIST_CONSOLIDATE_SYSTEM},
            {"role": "user", "content": ARCHIVIST_CONSOLIDATE_USER.format(
                entity_name=entity_name,
                entity_type=entity_type,
                fragments=fragments_text,
            )},
        ]

        try:
            from service.llm_client import llm_call
            from config.settings import Settings
            cfg = Settings().get_llm_config("memory", model=self.llm_model)
            result = llm_call(messages=messages, model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"] or self.api_key, base_url=cfg["base_url"])
            if result["status_code"] == 200:
                content = result["content"].strip()
                return self._parse_result(content)
            return None
        except Exception as e:
            logger.error(f"[Consolidator] LLM 调用失败: {e}")
            return None

    def _parse_result(self, content: str) -> Optional[Dict[str, Any]]:
        """解析 LLM 输出"""
        try:
            data = json.loads(content)
            if isinstance(data, dict) and 'content' in data:
                return data
            return None
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return data if isinstance(data, dict) and 'content' in data else None
                except json.JSONDecodeError:
                    pass
            return None

    def _index_episode_to_milvus(self, user_id: str, episode: Dict[str, Any]):
        """将剧集索引到 Milvus"""
        try:
            if not self.embedding_service or not self.milvus_service:
                return
            from .memory_milvus_service import MemoryMilvusService
            milvus = MemoryMilvusService(self.milvus_service.client, self.embedding_service)
            milvus.index_episodes(user_id, [episode])
        except Exception as e:
            logger.warning(f"[Consolidator] Milvus 索引失败: {e}")
