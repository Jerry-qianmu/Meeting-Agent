import logging
from typing import Dict, List

from service.retrieval_service import get_retrieval_service
from database.milvus.milvus_service import MilvusService
from ..state import KnowledgeAgentState
from ..structure_info.chunk import Chunk

logger = logging.getLogger(__name__)


def doc_retrieval(state: KnowledgeAgentState) -> dict:
    """
    直接检索：用 query 搜主 collection 的 chunk 内容
    """
    try:
        query = state.get("rewritten_query") or state["original_query"]
        config = state.get("config", {})
        strategy = state.get("retrieval_strategy") or config.get("retrieval_strategy", "hybrid")
        top_k = config.get("top_k", 10)
        # 内部搜索候选池：dense/BM25 各自取 search_limit 个候选再做 RRF 融合
        # 比 top_k 大可以显著提高融合质量，避免分数断层
        search_limit = config.get("search_limit", max(top_k * 5, 50))
        logger.info(f"[doc_retrieval] config.top_k={top_k}, search_limit={search_limit}, config keys={list(config.keys())}")

        target_kbs = state.get("target_knowledge_bases") or []
        target_docs = state.get("target_documents") or []

        if not target_kbs and not target_docs:
            logger.info("[doc_retrieval] 未指定知识库，使用模型自身知识")
            return _return_empty_results(strategy)

        # 1. 解析 collection 列表
        collection_names = _resolve_collections(target_kbs)
        if not collection_names:
            return _return_empty_results(strategy)

        # 2. 构建 doc_id filter
        filter_expr = _build_doc_filter(target_docs)

        retrieval = get_retrieval_service()

        all_chunks = []

        # 构建检索查询列表：主查询 + 子查询（如果有）
        queries_to_search = [query]
        sub_queries = state.get("sub_queries") or []
        if sub_queries:
            queries_to_search.extend(sub_queries)
            logger.info(f"[doc_retrieval] 子查询检索模式: 1 主查询 + {len(sub_queries)} 子查询")

        for collection_name in collection_names:
            try:
                for q in queries_to_search:
                    # ===== 新增调试日志 =====
                    logger.info(f"[doc_retrieval DEBUG] query='{q}'")
                    logger.info(f"[doc_retrieval DEBUG] collection='{collection_name}'")
                    logger.info(f"[doc_retrieval DEBUG] top_k={top_k}, filter_expr={filter_expr}, strategy={strategy}")
                    # ========================
                    results = retrieval.search(
                        query=q, collection=collection_name, top_k=top_k,
                        filter_expr=filter_expr, strategy=strategy,
                        search_limit=search_limit,
                    )
                    for r in results:
                        all_chunks.append(_to_chunk(r, strategy))

                    logger.info(
                        f"[doc_retrieval] {collection_name}: "
                        f"查询 '{q[:40]}...' 返回 {len(results)} 个 chunk"
                    )

            except Exception as e:
                logger.error(f"[doc_retrieval] collection {collection_name} 检索失败：{e}")

        # 3. 按 score 排序，截断到 top_k
        all_chunks.sort(key=lambda c: c.get("hybrid_score", 0.0) or c.get("vector_score", 0.0) or 0.0, reverse=True)
        merged_chunks = all_chunks[:top_k]

        # 4. 打印检索结果详情
        logger.info(f"[doc_retrieval] 最终返回 {len(merged_chunks)} 个 chunk")
        for i, c in enumerate(merged_chunks):
            score = c.get("hybrid_score", 0.0) or c.get("vector_score", 0.0) or 0.0
            content_preview = c.get("content", "")[:80].replace('\n', ' ')
            logger.info(
                f"  [{i+1}] score={score:.4f} | chunk_id={c.get('chunk_id', '')[:12]}... "
                f"| {content_preview}..."
            )

        return {
            "retrieval_results": {strategy: merged_chunks},
            "merged_chunks": merged_chunks,
            "retrieval_params": {
                "strategy": strategy, "top_k": top_k,
                "filter_expr": filter_expr,
                "target_kbs": target_kbs, "target_docs": target_docs,
                "collections_searched": collection_names,
            },
            "processing_log": [{
                "stage": "retrieval", "strategy": strategy,
                "query": query, "result_count": len(merged_chunks),
                "collections_searched": len(collection_names),
            }],
        }

    except Exception as e:
        logger.exception("[Retrieval Node] 执行失败")
        return {"retrieval_results": [], "processing_log": [{"stage": "retrieval", "error": str(e)}]}


def _resolve_collections(target_kbs: list) -> list:
    """将知识库 ID 列表解析为 Milvus collection 名称列表"""
    from database.mysql.repository.knowledge_base_repository import KnowledgeBaseRepository
    from database.mysql.mysql_client import get_db_client

    db_client = get_db_client()
    kb_repo = KnowledgeBaseRepository(db_client)
    collection_names = []

    for kb_id in target_kbs:
        kb_info = kb_repo.get_by_id(kb_id)
        if kb_info and kb_info.get('collection_name'):
            collection_names.append(kb_info['collection_name'])
        else:
            logger.warning(f"[doc_retrieval] 知识库不存在或无 collection: {kb_id}")

    return collection_names


def _build_doc_filter(target_docs: list) -> str:
    """构建 doc_id 过滤表达式"""
    if not target_docs:
        return None
    if len(target_docs) == 1:
        return f'doc_id == "{target_docs[0]}"'
    doc_ids = ",".join([f'"{d}"' for d in target_docs])
    return f"doc_id in [{doc_ids}]"


def _to_chunk(r: dict, strategy: str) -> Chunk:
    """将 Milvus 返回的原始数据转换为 Chunk 格式"""
    score = r.get("score", 0.0)
    metadata = r.get("metadata", {}) or {}
    return {
        "content": r.get("content", ""),
        "doc_id": r.get("doc_id", ""),
        "chunk_id": r.get("chunk_id", ""),
        "chunk_index": r.get("chunk_index", 0),
        "url": metadata.get("url"),
        "page": metadata.get("page"),
        "section": metadata.get("section"),
        "method": strategy,
        "vector_score": score if strategy == "vector_only" else None,
        "keyword_score": score if strategy == "keyword_only" else None,
        "hybrid_score": score if strategy == "hybrid" else None,
    }


def _return_empty_results(strategy: str) -> dict:
    return {
        "retrieval_results": {strategy: []},
        "merged_chunks": [],
        "retrieval_params": {
            "strategy": strategy, "top_k": 10,
            "filter_expr": None, "group_by": None,
            "target_kbs": [], "target_docs": [],
            "collections_searched": [],
        },
        "processing_log": [{"stage": "retrieval", "strategy": strategy, "result_count": 0}],
    }