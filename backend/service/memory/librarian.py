# -*- coding: utf-8 -*-
"""
InterviewLibrarian - 记忆检索器

三通道混合检索 + RRF 融合：关键词 + 向量 + 实体聚合
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .config import MemoryConfig

logger = logging.getLogger(__name__)


@dataclass
class RankedItem:
    id: str
    content: str
    source_type: str
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    importance_score: float = 0.0
    channel: str = "unknown"
    rank: int = 0
    rrf_score: float = 0.0


class InterviewLibrarian:
    """记忆检索器 - 三通道 RRF 融合"""

    def __init__(self, db_client, embedding_service=None, milvus_service=None):
        from database.mysql.repository.memory_fragment_repository import MemoryFragmentRepository
        from database.mysql.repository.memory_episode_repository import MemoryEpisodeRepository
        from database.mysql.repository.memory_entity_repository import MemoryEntityRepository
        from database.mysql.repository.cognitive_model_repository import CognitiveModelRepository

        self.fragment_repo = MemoryFragmentRepository(db_client)
        self.episode_repo = MemoryEpisodeRepository(db_client)
        self.entity_repo = MemoryEntityRepository(db_client)
        self.cognitive_repo = CognitiveModelRepository(db_client)
        self.embedding_service = embedding_service
        self.milvus_service = milvus_service

    def search(self, query: str, user_id: str,
               top_k: int = None) -> List[Dict[str, Any]]:
        """三通道检索 + RRF 融合"""
        if top_k is None:
            top_k = MemoryConfig.LIBRARIAN_TOP_K

        keyword_results = self._keyword_search(query, user_id)
        vector_results = self._vector_search(query, user_id)
        entity_results = self._entity_aggregation(query, user_id)

        fused = self._rrf_fusion(keyword_results, vector_results, entity_results)

        for item in fused:
            if item.source_type == 'episode':
                item.rrf_score *= MemoryConfig.LIBRARIAN_EPISODE_BOOST

        fused.sort(key=lambda x: x.rrf_score, reverse=True)
        top_results = fused[:top_k]

        return [
            {
                'id': r.id, 'content': r.content, 'source_type': r.source_type,
                'entity_id': r.entity_id, 'entity_name': r.entity_name,
                'importance_score': r.importance_score,
                'relevance_score': round(r.rrf_score, 4), 'channel': r.channel,
            }
            for r in top_results
        ]

    def _keyword_search(self, query: str, user_id: str) -> List[RankedItem]:
        items = []
        fragments = self.fragment_repo.search_by_keyword(user_id, query, limit=MemoryConfig.LIBRARIAN_TOP_K)
        for i, f in enumerate(fragments):
            items.append(RankedItem(
                id=f['fragment_id'], content=f['content'], source_type='fragment',
                entity_id=f.get('entity_id'), importance_score=f.get('importance_score', 0.5),
                channel='keyword', rank=i + 1,
            ))
        episodes = self.episode_repo.search_episodes(user_id, query, limit=MemoryConfig.LIBRARIAN_TOP_K)
        for i, e in enumerate(episodes):
            items.append(RankedItem(
                id=e['episode_id'], content=e['content'], source_type='episode',
                entity_id=e.get('entity_id'), importance_score=e.get('importance_score', 0.5),
                channel='keyword', rank=i + 1,
            ))
        return items

    def _vector_search(self, query: str, user_id: str) -> List[RankedItem]:
        if not self.milvus_service or not self.embedding_service:
            return []
        try:
            from .memory_milvus_service import MemoryMilvusService
            milvus = MemoryMilvusService(self.milvus_service.client, self.embedding_service)

            query_vector = self.embedding_service.embed_query(query)
            if not query_vector:
                return []

            items = []
            # 搜索碎片
            fragment_results = milvus.search(user_id, query_vector, MemoryConfig.LIBRARIAN_TOP_K, "fragment")
            for i, r in enumerate(fragment_results):
                items.append(RankedItem(
                    id=r['id'], content=r['content'], source_type='fragment',
                    entity_id=r.get('entity_id'), importance_score=r.get('importance_score', 0.5),
                    channel='vector', rank=i + 1,
                ))
            # 搜索剧集
            episode_results = milvus.search(user_id, query_vector, MemoryConfig.LIBRARIAN_TOP_K, "episode")
            for i, r in enumerate(episode_results):
                items.append(RankedItem(
                    id=r['id'], content=r['content'], source_type='episode',
                    entity_id=r.get('entity_id'), importance_score=r.get('importance_score', 0.5),
                    channel='vector', rank=i + 1,
                ))
            return items
        except Exception as e:
            logger.warning(f"[Librarian] 向量搜索失败: {e}")
            return []

    def _entity_aggregation(self, query: str, user_id: str) -> List[RankedItem]:
        entities = self.entity_repo.search_entities(user_id, query, limit=5)
        if not entities:
            return []
        items = []
        rank = 1
        for entity in entities:
            episodes = self.episode_repo.get_entity_episodes(entity['entity_id'], limit=3)
            for ep in episodes:
                items.append(RankedItem(
                    id=ep['episode_id'], content=ep['content'], source_type='episode',
                    entity_id=entity['entity_id'], entity_name=entity['name'],
                    importance_score=ep.get('importance_score', 0.5),
                    channel='entity', rank=rank,
                ))
                rank += 1
            fragments = self.fragment_repo.get_user_fragments(user_id, entity_id=entity['entity_id'], limit=3)
            for frag in fragments:
                items.append(RankedItem(
                    id=frag['fragment_id'], content=frag['content'], source_type='fragment',
                    entity_id=entity['entity_id'], entity_name=entity['name'],
                    importance_score=frag.get('importance_score', 0.5),
                    channel='entity', rank=rank,
                ))
                rank += 1
        return items

    def _rrf_fusion(self, *result_lists: List[RankedItem], k: int = None) -> List[RankedItem]:
        if k is None:
            k = MemoryConfig.LIBRARIAN_RRF_K
        score_map: Dict[str, float] = {}
        item_map: Dict[str, RankedItem] = {}
        for channel_results in result_lists:
            for item in channel_results:
                rrf = 1.0 / (k + item.rank)
                if item.id in score_map:
                    score_map[item.id] += rrf
                else:
                    score_map[item.id] = rrf
                    item_map[item.id] = item
        results = []
        for item_id, score in score_map.items():
            item = item_map[item_id]
            item.rrf_score = score
            results.append(item)
        return results

    def get_cognitive_profile(self, user_id: str) -> str:
        """获取候选人认知画像文本"""
        profile = self.cognitive_repo.get_profile_summary(user_id)
        if not profile:
            return ""
        lines = ["【候选人画像】"]
        for dim, entries in profile.items():
            for entry in entries[:2]:
                lines.append(f"- {dim}/{entry['key']}: {entry['value']} (置信度:{entry['confidence']:.1f})")
        return "\n".join(lines)
