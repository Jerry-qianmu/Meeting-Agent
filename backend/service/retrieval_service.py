# -*- coding: utf-8 -*-
"""
Retrieval Service - Milvus 混合检索
"""
from typing import List, Optional
import logging
import os,sys
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.append(parent_dir)
from database.milvus.milvus_service import get_milvus_service

logger = logging.getLogger(__name__)


class RetrievalService:
    """统一检索入口（vector / keyword / hybrid）"""

    def __init__(self):
        self.milvus = get_milvus_service()

    # =========================
    # 1️⃣ 纯语义检索
    # =========================
    def vector_search(
        self,
        query: str,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
        collection: Optional[str] = None,
    ) -> List[dict]:
        """纯 dense 向量检索"""
        if not collection:
            logger.warning("[Retrieval] collection 未指定")
            return []

        return self.milvus.vector_search(
            collection_name=collection,
            query=query,
            top_k=top_k,
            filter_expr=filter_expr,
        )

    # =========================
    # 2️⃣ 纯关键词检索（BM25）
    # =========================
    def keyword_search(
        self,
        query: str,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
        collection: Optional[str] = None,
        use_text_match_filter: bool = False,
    ) -> List[dict]:
        """纯关键词检索（BM25）"""

        if not collection:
            logger.warning("[Retrieval] collection 未指定")
            return []

        return self.milvus.keyword_search(
            collection_name=collection,
            query=query,
            top_k=top_k,
            filter_expr=filter_expr,
            use_text_match_filter=use_text_match_filter,
        )

    # =========================
    # 3️⃣ 混合检索（默认主入口）
    # =========================
    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
        collection: Optional[str] = None,
        keyword_filter: Optional[str] = None,
        group_by_field: Optional[str] = None,  # 默认不分组
        group_size: int = 5,
        strict_group_size: bool = False,
        ranker: str = "RRF",
        rrf_k: int = 60,
        hybrid_alpha: float = 0.5,
        search_limit: Optional[int] = None,
    ) -> List[dict]:
        """Dense + BM25 混合检索（推荐默认）"""

        if not collection:
            logger.warning("[Retrieval] collection 未指定")
            return []

        return self.milvus.hybrid_search(
            collection_name=collection,
            query=query,
            top_k=top_k,
            filter_expr=filter_expr,
            keyword_filter=keyword_filter,
            group_by_field=group_by_field,
            group_size=group_size,
            strict_group_size=strict_group_size,
            ranker=ranker,
            rrf_k=rrf_k,
            hybrid_alpha=hybrid_alpha,
            search_limit=search_limit,
        )

    # =========================
    # 4️⃣ 统一入口（推荐用这个）
    # =========================
    def search(
        self,
        query: str,
        collection: str,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
        strategy: str = "hybrid",  # vector_only / keyword_only / hybrid
        **kwargs,
    ) -> List[dict]:
        """统一检索入口（根据 strategy 自动分发）"""

        if not collection:
            logger.warning("[Retrieval] collection 未指定")
            return []

        if strategy == "vector_only":
            return self.vector_search(
                query=query,
                top_k=top_k,
                filter_expr=filter_expr,
                collection=collection,
            )

        elif strategy == "keyword_only":
            return self.keyword_search(
                query=query,
                top_k=top_k,
                filter_expr=filter_expr,
                collection=collection,
                use_text_match_filter=True,  # keyword 场景建议开启
            )

        else:  # 默认 hybrid
            return self.hybrid_search(
                query=query,
                top_k=top_k,
                filter_expr=filter_expr,
                collection=collection,
                **kwargs,
            )


_retrieval_service = None


def get_retrieval_service() -> RetrievalService:
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service
