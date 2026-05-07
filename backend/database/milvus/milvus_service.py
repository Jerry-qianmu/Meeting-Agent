"""
Milvus 向量数据库服务
负责 collection 管理、向量写入、混合检索、删除
"""
import logging
from typing import Any, Dict, List, Optional
import sys,os

from pymilvus import (
    MilvusClient,
    DataType,
    Function,
    FunctionType,
    AnnSearchRequest,
    RRFRanker,
    WeightedRanker,
)

logger = logging.getLogger(__name__)
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.append(grand_parent_dir)

from config.settings import Settings
settings = Settings()

from service.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)

_ANALYZER_PARAMS = {"type": "chinese"}

class MilvusService:

    def __init__(self):
        uri = f"http://{settings.milvus_host}:{settings.milvus_port}"
        token = f"{settings.milvus_user}:{settings.milvus_password}"
        self.client = MilvusClient(uri=uri, token=token)
        logger.info(f"Milvus 连接成功: {uri}")

    # ── Collection 管理 ───────────────────────────────────────────────────────

    def get_or_create_collection(
            self,
            collection_name: str,
            dim: int = 1536,
            metadata_fields: Optional[List[Dict[str, Any]]] = None,
        ) -> None:
            """幂等创建文本知识库 collection（支持 dense + BM25 + fulltext）

            metadata_fields 示例：
            [
                {"key": "title", "fulltext": True, "index": False},
                {"key": "author", "fulltext": False, "index": True},
            ]
            """

            if self.client.has_collection(collection_name):
                logger.info(f"Collection 已存在：{collection_name}")
                # 已存在的 collection 不需要再次创建，直接 load
                try:
                    self.client.load_collection(collection_name)
                    logger.info(f"Collection 已加载：{collection_name}")
                except Exception as e:
                    logger.warning(f"加载 collection 失败：{e}")
                return

            # === Schema ===
            schema = MilvusClient.create_schema(enable_dynamic_field=True)

            # 主键
            schema.add_field("chunk_id", DataType.VARCHAR, max_length=64, is_primary=True)

            # 文档结构
            schema.add_field("doc_id", DataType.VARCHAR, max_length=128)
            schema.add_field("job_id", DataType.VARCHAR, max_length=128)
            schema.add_field("chunk_index", DataType.INT64)

            # 文本内容
            schema.add_field(
                "content",
                DataType.VARCHAR,
                max_length=32768,
                enable_analyzer=True,
                analyzer_params=_ANALYZER_PARAMS,
                enable_match=True,
            )

            # 向量字段
            schema.add_field("dense", DataType.FLOAT_VECTOR, dim=dim)
            schema.add_field("sparse_bm25", DataType.SPARSE_FLOAT_VECTOR)

            # === 用户自定义 metadata（避免与已有字段重复）===
            existing_fields = {"chunk_id", "doc_id", "job_id", "chunk_index", "content", "dense", "sparse_bm25"}
            for mf in (metadata_fields or []):
                key = mf.get("key")
                if not key:
                    continue
                
                # 跳过已存在的字段
                if key in existing_fields:
                    logger.warning(f"[Milvus] 跳过重复字段：{key}（已内置）")
                    continue

                # fulltext 字段
                if mf.get("fulltext"):
                    schema.add_field(
                        key,
                        DataType.VARCHAR,
                        max_length=1024,
                        enable_analyzer=True,
                        analyzer_params=_ANALYZER_PARAMS,
                        enable_match=True,
                        nullable=True,
                    )
                    logger.info(f"[Milvus] 元数据字段 '{key}'（fulltext）已加入 schema")
                    existing_fields.add(key)

                else:
                    # 普通字段（用于 filter）
                    schema.add_field(
                        key,
                        DataType.VARCHAR,
                        max_length=512,
                        nullable=True,
                    )
                    logger.info(f"[Milvus] 元数据字段 '{key}'（filter）已加入 schema")
                    existing_fields.add(key)

            # === BM25 function ===
            schema.add_function(Function(
                name="bm25",
                function_type=FunctionType.BM25,
                input_field_names=["content"],
                output_field_names="sparse_bm25",
            ))

            # === Index ===
            index_params = self.client.prepare_index_params()

            # dense 向量索引
            index_params.add_index(
                field_name="dense",
                index_name="dense_hnsw",
                index_type="HNSW",
                metric_type="IP",
                params={"M": 16, "efConstruction": 200},
            )

            # BM25 稀疏索引
            index_params.add_index(
                field_name="sparse_bm25",
                index_name="sparse_bm25_idx",
                index_type="SPARSE_WAND",
                metric_type="BM25",
            )

            # metadata filter 索引（可选）
            for mf in (metadata_fields or []):
                if mf.get("index") and mf.get("key"):
                    index_params.add_index(
                        field_name=mf["key"],
                        index_type="INVERTED",
                    )
                    logger.info(f"[Milvus] 元数据字段 '{mf['key']}' 已创建倒排索引")

            # === 创建 collection ===
            self.client.create_collection(
                collection_name=collection_name,
                schema=schema,
                index_params=index_params,
            )

            # ⚠️ 强烈建议 load
            self.client.load_collection(collection_name)

            logger.info(f"Collection 创建并加载成功: {collection_name}")

    def delete_collection(self, collection_name: str) -> None:
        if self.client.has_collection(collection_name):
            self.client.drop_collection(collection_name)
            logger.info(f"Collection 已删除: {collection_name}")

    def list_collections(self) -> List[str]:
        return self.client.list_collections()

    def has_collection(self, collection_name: str) -> bool:
        return self.client.has_collection(collection_name)

        # ── 数据写入 ──────────────────────────────────────────────────────────────

    def upsert_chunks(
        self,
        collection_name: str,
        chunks: List[Dict[str, Any]],
        vector_dim: Optional[int] = None,
        embedding_model: Optional[str] = None,
        metadata_fields: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        批量 upsert 切片到 Milvus（文本专用版本）

        metadata_fields:
        fulltext=True 的字段会拼接到 content 前面参与 BM25 和 dense 检索
        """

        if not chunks:
            return {"upsert_count": 0}

        # === 找出需要拼接的 fulltext 字段 ===
        fulltext_keys = [
            mf["key"] for mf in (metadata_fields or [])
            if mf.get("fulltext") and mf.get("key")
        ]

        embedding_svc = get_embedding_service()

        # 临时切换 embedding 模型
        original_model = embedding_svc.model
        if embedding_model and embedding_model != original_model:
            embedding_svc.model = embedding_model

        try:
            texts = []

            for c in chunks:
                base_content = c["content"]
                meta = c.get("metadata") or {}

                # 拼接 fulltext metadata（仅用于检索）
                if fulltext_keys:
                    prefix_parts = [
                        f"{k}：{meta[k]}" for k in fulltext_keys if meta.get(k)
                    ]
                    if prefix_parts:
                        indexed_content = "\n".join(prefix_parts) + "\n\n" + base_content
                    else:
                        indexed_content = base_content
                else:
                    indexed_content = base_content

                texts.append(indexed_content)

            vectors = embedding_svc.embed_texts(texts, dimension=vector_dim)

        finally:
            embedding_svc.model = original_model

        # === 校验 ===
        if len(vectors) != len(chunks):
            raise RuntimeError(f"Embedding 数量不匹配: {len(vectors)} vs {len(chunks)}")

        if vectors and vector_dim and len(vectors[0]) != vector_dim:
            raise RuntimeError(
                f"向量维度不匹配：期望 {vector_dim}，实际 {len(vectors[0])}"
            )

        # === 构造写入数据 ===
        data = []

        for chunk, vec, indexed_content in zip(chunks, vectors, texts):
            row: Dict[str, Any] = {
                "chunk_id":    chunk["chunk_id"],
                "doc_id":      chunk.get("doc_id", ""),   # ✅ 新核心字段
                "job_id":      chunk.get("job_id", ""),
                "chunk_index": int(chunk.get("chunk_index", 0)),
                "content":     indexed_content,           # 用于检索（含 metadata 拼接）
                "dense":       vec,
            }

          # === metadata 写入（不覆盖已有字段）===
            for k, v in (chunk.get("metadata") or {}).items():
                if k not in row:
                    # 将 int/float 转换为字符串，因为 Milvus schema 中用户自定义字段默认为 VARCHAR
                    if isinstance(v, (int, float)):
                        row[k] = str(v)
                    else:
                        row[k] = v

            data.append(row)

        # === 批量 upsert ===
        batch_size = 200
        total = 0

        for i in range(0, len(data), batch_size):
            batch = data[i: i + batch_size]
            res = self.client.upsert(
                collection_name=collection_name,
                data=batch
            )
            total += res.get("upsert_count", len(batch))

        logger.info(f"[Milvus] upsert {total} 条到 {collection_name}")

        return {"upsert_count": total}

    # ── 删除 ──────────────────────────────────────────────────────────────────

    def delete_by_job(self, collection_name: str, job_id: str) -> None:
        if not self.client.has_collection(collection_name):
            return
        self.client.delete(
            collection_name=collection_name,
            filter=f'job_id == "{job_id}"',
        )
        logger.info(f"[Milvus] 删除 job_id={job_id} from {collection_name}")

    def delete_by_doc_id(self, collection_name: str, doc_id: str) -> None:
        if not self.client.has_collection(collection_name):
            return

        escaped = doc_id.replace('"', '\\"')

        self.client.delete(
            collection_name=collection_name,
            filter=f'doc_id == "{escaped}"',
        )

        logger.info(f"[Milvus] 删除 doc_id={doc_id} from {collection_name}")
    
    def get_chunk_by_id(self, collection_name: str, chunk_id: str) -> Optional[Dict[str, Any]]:
        """根据 chunk_id 获取单个 chunk 的数据（含向量）"""
        if not self.client.has_collection(collection_name):
            return None
        
        try:
            # 查询该 chunk 的所有字段（包括 dense 向量）
            results = self.client.query(
                collection_name=collection_name,
                filter=f'chunk_id == "{chunk_id}"',
                output_fields=["*", "dense"]  # * 包含所有标量字段，dense 是向量
            )
            
            if results and len(results) > 0:
                return results[0]
            return None
        except Exception as e:
            logger.warning(f"查询 chunk 失败：chunk_id={chunk_id}, error={e}")
            return None

    def delete_by_chunk_ids(self, collection_name: str, chunk_ids: List[str]) -> None:
        if not chunk_ids or not self.client.has_collection(collection_name):
            return
        ids_str = ", ".join(f'"{cid}"' for cid in chunk_ids)
        self.client.delete(
            collection_name=collection_name,
            filter=f"chunk_id in [{ids_str}]",
        )

    # ── 检索 ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_text_match_filter(keywords: str, base_filter: Optional[str] = None) -> str:
        """把关键词字符串构建成 TEXT_MATCH filter，多词之间 OR 逻辑"""
        text_match = f"TEXT_MATCH(content, '{keywords}')"
        if base_filter:
            return f"({base_filter}) and {text_match}"
        return text_match


    def hybrid_search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
        ranker: str = "RRF",
        rrf_k: int = 60,
        hybrid_alpha: float = 0.5,
        keyword_filter: Optional[str] = None,
        group_by_field: Optional[str] = "doc_id",  # ✅ 默认按文档分组
        group_size: int = 1,
        strict_group_size: bool = False,
        query_text_vector: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        """Dense + BM25 混合检索（文本专用）"""

        if not self.client.has_collection(collection_name):
            logger.warning(f"[Milvus] collection 不存在: {collection_name}")
            return []

        # === 构建 filter ===
        if keyword_filter:
            final_filter = self._build_text_match_filter(keyword_filter, filter_expr)
        else:
            final_filter = filter_expr

        # === query embedding ===
        query_vector = (
            query_text_vector
            if query_text_vector
            else get_embedding_service().embed_query(query)
        )

        # === dense 检索 ===
        dense_kwargs: Dict[str, Any] = {
            "data": [query_vector],
            "anns_field": "dense",
            "param": {"metric_type": "IP", "params": {"ef": 100}},
            "limit": top_k,
        }
        if final_filter:
            dense_kwargs["expr"] = final_filter

        # === BM25 检索 ===
        bm25_kwargs: Dict[str, Any] = {
            "data": [query],
            "anns_field": "sparse_bm25",
            "param": {"metric_type": "BM25", "params": {"drop_ratio_search": 0.2}},
            "limit": top_k,
        }
        if final_filter:
            bm25_kwargs["expr"] = final_filter

        # === 融合策略 ===
        if ranker == "Weight":
            sparse_weight = round(1.0 - hybrid_alpha, 2)
            reranker = WeightedRanker(hybrid_alpha, sparse_weight)
        else:
            reranker = RRFRanker(k=rrf_k)

        # === 输出字段 ===
        output_fields = ["chunk_id", "doc_id", "job_id", "chunk_index", "content"]

        # === 构建请求 ===
        reqs = [
            AnnSearchRequest(**dense_kwargs),
            AnnSearchRequest(**bm25_kwargs),
        ]

        search_kwargs: Dict[str, Any] = {
            "collection_name": collection_name,
            "reqs": reqs,
            "ranker": reranker,
            "limit": top_k,
            "output_fields": output_fields,
        }

        # === 分组（避免一个文档占满）===
        if group_by_field:
            search_kwargs["group_by_field"] = group_by_field
            search_kwargs["group_size"] = group_size
            search_kwargs["strict_group_size"] = strict_group_size

        # === 执行查询 ===
        try:
            results = self.client.hybrid_search(**search_kwargs)
        except Exception as e:
            logger.error(f"[Milvus] hybrid_search 失败: {e}")
            raise

        # === 解析结果 ===
        hits = []
        for hit in (results[0] if results else []):
            entity = hit.get("entity", {})

            hits.append({
                "chunk_id":    entity.get("chunk_id") or hit.get("id"),
                "doc_id":      entity.get("doc_id", ""),
                "job_id":      entity.get("job_id", ""),
                "chunk_index": entity.get("chunk_index", 0),
                "content":     entity.get("content", ""),
                "score":       hit.get("distance", 0.0),
                "retrieval_source": "hybrid",
                "metadata": {
                    k: v for k, v in entity.items()
                    if k not in ("chunk_id", "doc_id", "job_id", "chunk_index", "content")
                },
            })

        mode = "keyword_filter+hybrid" if keyword_filter else "hybrid"
        logger.info(f"[Milvus] {mode} 返回 {len(hits)} 条 (collection={collection_name})")

        return hits


    def vector_search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """纯 dense 向量检索"""

        if not self.client.has_collection(collection_name):
            return []

        query_vector = get_embedding_service().embed_query(query)

        search_kwargs: Dict[str, Any] = {
            "collection_name": collection_name,
            "data": [query_vector],
            "anns_field": "dense",
            "search_params": {"metric_type": "IP", "params": {"ef": 100}},
            "limit": top_k,
            "output_fields": ["chunk_id", "doc_id", "job_id", "chunk_index", "content"],
        }

        if filter_expr:
            search_kwargs["filter"] = filter_expr

        results = self.client.search(**search_kwargs)

        hits = []
        for hit in (results[0] if results else []):
            entity = hit.get("entity", {})

            hits.append({
                "chunk_id":    entity.get("chunk_id") or hit.get("id"),
                "doc_id":      entity.get("doc_id", ""),
                "job_id":      entity.get("job_id", ""),
                "chunk_index": entity.get("chunk_index", 0),
                "content":     entity.get("content", ""),
                "score":       hit.get("distance", 0.0),
                "metadata": {
                    k: v for k, v in entity.items()
                    if k not in ("chunk_id", "doc_id", "job_id", "chunk_index", "content")
                },
            })

        return hits
    
    def keyword_search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
        group_by_field: Optional[str] = "doc_id",
        group_size: int = 1,
        strict_group_size: bool = False,
        use_text_match_filter: bool = False,
    ) -> List[Dict[str, Any]]:
        """纯关键词检索（BM25）

        use_text_match_filter:
            True → 先用 TEXT_MATCH 预过滤，再做 BM25
            False → 直接 BM25
        """

        if not self.client.has_collection(collection_name):
            logger.warning(f"[Milvus] collection 不存在: {collection_name}")
            return []

        # === 构建 filter ===
        final_filter = filter_expr
        if use_text_match_filter:
            final_filter = self._build_text_match_filter(query, filter_expr)

        # === BM25 检索 ===
        search_kwargs: Dict[str, Any] = {
            "collection_name": collection_name,
            "data": [query],
            "anns_field": "sparse_bm25",
            "param": {
                "metric_type": "BM25",
                "params": {"drop_ratio_search": 0.2}
            },
            "limit": top_k,
            "output_fields": ["chunk_id", "doc_id", "job_id", "chunk_index", "content"],
        }

        if final_filter:
            search_kwargs["expr"] = final_filter

        # === 分组（避免单文档占满）===
        if group_by_field:
            search_kwargs["group_by_field"] = group_by_field
            search_kwargs["group_size"] = group_size
            search_kwargs["strict_group_size"] = strict_group_size

        # === 执行查询 ===
        try:
            results = self.client.search(**search_kwargs)
        except Exception as e:
            logger.error(f"[Milvus] keyword_search 失败: {e}")
            raise

        # === 解析结果 ===
        hits = []
        for hit in (results[0] if results else []):
            entity = hit.get("entity", {})

            hits.append({
                "chunk_id":    entity.get("chunk_id") or hit.get("id"),
                "doc_id":      entity.get("doc_id", ""),
                "job_id":      entity.get("job_id", ""),
                "chunk_index": entity.get("chunk_index", 0),
                "content":     entity.get("content", ""),
                "score":       hit.get("distance", 0.0),  # BM25 score
                "retrieval_source": "keyword",
                "metadata": {
                    k: v for k, v in entity.items()
                    if k not in ("chunk_id", "doc_id", "job_id", "chunk_index", "content")
                },
            })

        mode = "text_match+bm25" if use_text_match_filter else "bm25"
        logger.info(f"[Milvus] {mode} 返回 {len(hits)} 条 (collection={collection_name})")

        return hits


_instance: Optional[MilvusService] = None


def get_milvus_service() -> MilvusService:
    global _instance
    if _instance is None:
        _instance = MilvusService()
    return _instance