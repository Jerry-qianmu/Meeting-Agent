# -*- coding: utf-8 -*-
"""
Memory Milvus Service - 记忆向量索引服务

为碎片和剧集提供 Milvus dense + BM25 混合索引
"""

import logging
from typing import List, Dict, Any

from pymilvus import MilvusClient, DataType, Function, FunctionType

from .config import MemoryConfig

logger = logging.getLogger(__name__)

_ANALYZER_PARAMS = {"type": "chinese"}


class MemoryMilvusService:

    def __init__(self, milvus_client: MilvusClient, embedding_service):
        self.client = milvus_client
        self.embedding_service = embedding_service
        # 从 embedding service 获取实际维度，而非硬编码
        self._vector_dim = getattr(embedding_service, 'dimension', 1536)

    @staticmethod
    def _sanitize_user_id(user_id: str) -> str:
        """Milvus 集合名只能含数字字母下划线，替换连字符"""
        return user_id.replace("-", "_")

    def ensure_fragment_collection(self, user_id: str) -> str:
        name = MemoryConfig.MEMORY_FRAGMENTS_COLLECTION.format(
            user_id=self._sanitize_user_id(user_id))
        self._ensure_collection(name, "fragment_id",
                                ["entity_id", "fragment_type", "importance_score"])
        return name

    def ensure_episode_collection(self, user_id: str) -> str:
        name = MemoryConfig.MEMORY_EPISODES_COLLECTION.format(
            user_id=self._sanitize_user_id(user_id))
        self._ensure_collection(name, "episode_id",
                                ["entity_id", "episode_type", "importance_score"])
        return name

    def _ensure_collection(self, collection_name: str, id_field: str,
                           filter_fields: List[str]):
        if self.client.has_collection(collection_name):
            try:
                self.client.load_collection(collection_name)
            except Exception:
                pass
            return

        schema = self.client.create_schema(enable_dynamic_field=True)
        schema.add_field(id_field, DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("content", DataType.VARCHAR, max_length=4096,
                         enable_analyzer=True, analyzer_params=_ANALYZER_PARAMS, enable_match=True)
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=self._vector_dim)
        schema.add_field("sparse_bm25", DataType.SPARSE_FLOAT_VECTOR)
        for ff in filter_fields:
            schema.add_field(ff, DataType.VARCHAR, max_length=256, nullable=True)

        schema.add_function(Function(
            name="bm25", function_type=FunctionType.BM25,
            input_field_names=["content"], output_field_names="sparse_bm25",
        ))

        index_params = self.client.prepare_index_params()
        index_params.add_index(field_name="dense", index_name="dense_hnsw",
                               index_type="HNSW", metric_type="IP",
                               params={"M": 16, "efConstruction": 200})
        index_params.add_index(field_name="sparse_bm25", index_name="sparse_bm25_idx",
                               index_type="SPARSE_WAND", metric_type="BM25")
        for ff in filter_fields:
            index_params.add_index(field_name=ff, index_type="INVERTED")

        self.client.create_collection(
            collection_name=collection_name, schema=schema, index_params=index_params)
        self.client.load_collection(collection_name)
        logger.info(f"[MemoryMilvus] 创建集合: {collection_name}")

    def index_fragments(self, user_id: str, fragments: List[Dict[str, Any]]):
        if not fragments:
            return
        collection_name = self.ensure_fragment_collection(user_id)
        self._index_items(collection_name, "fragment_id", fragments)

    def index_episodes(self, user_id: str, episodes: List[Dict[str, Any]]):
        if not episodes:
            return
        collection_name = self.ensure_episode_collection(user_id)
        self._index_items(collection_name, "episode_id", episodes)

    def _index_items(self, collection_name: str, id_field: str,
                     items: List[Dict[str, Any]]):
        texts = [item['content'] for item in items]
        try:
            vectors = self.embedding_service.embed_texts(texts, dimension=self._vector_dim)
        except Exception as e:
            logger.warning(f"[MemoryMilvus] Embedding 失败: {e}")
            return

        if len(vectors) != len(items):
            return

        data = []
        for item, vec in zip(items, vectors):
            row = {id_field: item[id_field], "content": item['content'], "dense": vec}
            if item.get('entity_id'):
                row['entity_id'] = item['entity_id']
            type_field = 'fragment_type' if 'fragment_type' in item else 'episode_type'
            if item.get(type_field):
                row[type_field] = item[type_field]
            data.append(row)

        try:
            self.client.upsert(collection_name=collection_name, data=data)
            logger.info(f"[MemoryMilvus] 索引 {len(data)} 条到 {collection_name}")
        except Exception as e:
            logger.warning(f"[MemoryMilvus] Upsert 失败: {e}")

    def search(self, user_id: str, query_vector: List[float],
               top_k: int = 10, source_type: str = "fragment") -> List[Dict[str, Any]]:
        uid = self._sanitize_user_id(user_id)
        if source_type == "fragment":
            collection_name = MemoryConfig.MEMORY_FRAGMENTS_COLLECTION.format(user_id=uid)
            id_field = "fragment_id"
        else:
            collection_name = MemoryConfig.MEMORY_EPISODES_COLLECTION.format(user_id=uid)
            id_field = "episode_id"

        if not self.client.has_collection(collection_name):
            return []

        try:
            results = self.client.search(
                collection_name=collection_name, data=[query_vector],
                limit=top_k, anns_field="dense",
                output_fields=[id_field, "content", "entity_id", "importance_score"],
                search_params={"metric_type": "IP"},
            )
            items = []
            for hits in results:
                for hit in hits:
                    entity = hit.get('entity', {})
                    raw_score = entity.get('importance_score')
                    items.append({
                        'id': entity.get(id_field, ''),
                        'content': entity.get('content', ''),
                        'entity_id': entity.get('entity_id'),
                        'importance_score': float(raw_score) if raw_score is not None else 0.5,
                        'score': hit.get('distance', 0),
                        'source_type': source_type,
                    })
            return items
        except Exception as e:
            logger.warning(f"[MemoryMilvus] 搜索失败: {e}")
            return []
