import os,sys
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.append(os.path.dirname(grand_parent_dir))
sys.path.append(os.path.dirname(parent_dir))
from backend.service.retrieval_service import get_retrieval_service
import logging
logger = logging.getLogger(__name__)
from ..state import KnowledgeAgentState
def doc_retrieval(state: KnowledgeAgentState) -> dict:
    try:
        query = state.get("rewritten_query") or state["original_query"]
        
        # 从 config 中获取配置
        config = state.get("config", {})
        
        strategy = config.get("retrieval_strategy", "hybrid")
        top_k = config.get("top_k", 10)

        # 获取目标知识库和文档
        target_kbs = state.get("target_knowledge_bases") or []
        target_docs = state.get("target_documents") or []
        
        # 关键修改：如果用户没有指定任何知识库或文档，直接返回空结果
        # 这样 Agent 会使用模型自身知识回答，而不是检索所有知识库
        if not target_kbs and not target_docs:
            logger.info("[doc_retrieval] 用户未指定知识库或文档，使用模型自身知识回答（不检索）")
            return _return_empty_results(strategy)
        
        # 根据目标知识库获取 collection 名称列表
        collection_names = []
        if target_kbs:
            # 用户指定了知识库：只检索这些知识库
            from database.mysql.repository.knowledge_base_repository import KnowledgeBaseRepository
            from database.mysql.mysql_client import get_db_client
            
            db_client = get_db_client()
            kb_repo = KnowledgeBaseRepository(db_client)
            
            # 获取所有目标知识库的 collection_name
            for kb_id in target_kbs:
                kb_info = kb_repo.get_by_id(kb_id)
                if kb_info and kb_info.get('collection_name'):
                    collection_names.append(kb_info['collection_name'])
                    logger.info(f"[doc_retrieval] 知识库 {kb_id} 的 collection: {kb_info['collection_name']}")
                else:
                    logger.warning(f"[doc_retrieval] 知识库不存在或无 collection: {kb_id}")
            
            if not collection_names:
                logger.error(f"[doc_retrieval] 未找到任何有效的 collection，目标知识库：{target_kbs}")
                return _return_empty_results(strategy)
        
        else:
            # 用户没有指定任何知识库
            # 默认检索所有知识库的所有内容
            logger.info("[doc_retrieval] 未指定知识库，检索所有知识库")
            from database.mysql.repository.knowledge_base_repository import KnowledgeBaseRepository
            from database.mysql.mysql_client import get_db_client
            
            db_client = get_db_client()
            kb_repo = KnowledgeBaseRepository(db_client)
            
            # 获取所有可用的知识库
            all_kbs = kb_repo.get_all_knowledge_bases()
            for kb in all_kbs:
                if kb.get('collection_name'):
                    collection_names.append(kb['collection_name'])
                    logger.debug(f"[doc_retrieval] 知识库 {kb.get('kb_uuid')} 的 collection: {kb['collection_name']}")
            
            logger.info(f"[doc_retrieval] 共加载 {len(collection_names)} 个知识库的 collection")
            
            if not collection_names:
                logger.warning("[doc_retrieval] 数据库中没有任何知识库")
        
        logger.info(f"[doc_retrieval] 目标知识库：{len(target_kbs)}, 目标文档：{len(target_docs)}, Collections: {len(collection_names)}")
        
        retrieval = get_retrieval_service()

      # =========================
        # 1️⃣ 构建 filter + group
        # =========================
        filter_conditions = []
        group_by_field = None

        # 添加文档过滤条件（知识库过滤在每个 collection 中自动满足）
        if len(target_docs) == 1:
            filter_conditions.append(f'doc_id == "{target_docs[0]}"')
        elif len(target_docs) > 1:
            doc_ids = ",".join([f'"{d}"' for d in target_docs])
            filter_conditions.append(f"doc_id in [{doc_ids}]")
            group_by_field = "doc_id"
        elif not target_docs:
            # 如果没有指定文档，按文档分组
            group_by_field = "doc_id"
        
        # 合并所有过滤条件
        filter_expr = " and ".join(filter_conditions) if filter_conditions else None
        
        logger.info(f"[doc_retrieval] 过滤条件：{filter_expr}")

        # =========================
        # 2️⃣ 跨 collection 检索
        # =========================
        all_results = []
        
        # 每个 collection 检索 top_k * 2 个结果，以便后续合并和重排序
        per_collection_top_k = top_k * 2 if len(collection_names) > 1 else top_k
        
        for collection_name in collection_names:
            try:
                # 为每个 collection 构建搜索参数
                search_kwargs = {
                    "query": query,
                    "collection": collection_name,
                    "top_k": per_collection_top_k,
                    "filter_expr": filter_expr,
                    "strategy": strategy,
                    "group_by_field": group_by_field,
                    "group_size": 1,
                    "rrf_k": config.get("rrf_k", 60),
                    "hybrid_alpha": config.get("hybrid_alpha", 0.5),
                }
                
                logger.info(f"[doc_retrieval] 检索 collection: {collection_name}")
                collection_results = retrieval.search(**search_kwargs)
                logger.info(f"[doc_retrieval] collection {collection_name} 返回 {len(collection_results)} 条结果")
                
                # 添加 collection 来源标记
                for result in collection_results:
                    result['_collection'] = collection_name
                
                all_results.extend(collection_results)
                
            except Exception as e:
                logger.error(f"[doc_retrieval] collection {collection_name} 检索失败：{e}")
        
        logger.info(f"[doc_retrieval] 跨 collection 检索完成，共 {len(all_results)} 条结果")
        
        # =========================
        # 3️⃣ 合并结果（如果跨多个 collection）
        # =========================
        if len(collection_names) > 1 and all_results:
            # 跨多个 collection 时，需要去重和合并
            seen_chunk_ids = set()
            merged_results = []
            
            for result in all_results:
                chunk_id = result.get("chunk_id")
                if chunk_id and chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk_id)
                    merged_results.append(result)
            
            # 限制最终结果数量
            if len(merged_results) > top_k:
                merged_results = merged_results[:top_k]
            
            logger.info(f"[doc_retrieval] 去重后剩余 {len(merged_results)} 条结果")
            all_results = merged_results

       # =========================
        # 3️⃣ 执行检索（已在上一步完成）
        # =========================
        results = all_results

        from agents.knowledge.structure_info.chunk import Chunk
        from typing import List,Dict
        chunks: List[Chunk] = []

        for r in results:
            score = r.get("score", 0.0)
            metadata = r.get("metadata", {}) or {}

            chunk: Chunk = {
                # content
                "content": r.get("content", ""),

                # source
                "doc_id": r.get("doc_id", ""),
                "chunk_id": r.get("chunk_id", ""),
                "chunk_index": r.get("chunk_index", 0),

                # document info（从 metadata 拆）
                "url": metadata.get("url"),
                "page": metadata.get("page"),
                "section": metadata.get("section"),

                # retrieval info
                "method": strategy,
                "vector_score": score if strategy == "vector_only" else None,
                "keyword_score": score if strategy == "keyword_only" else None,
                "hybrid_score": score if strategy == "hybrid" else None,
            }
            chunks.append(chunk)

        retrieval_results: Dict[str, List[Chunk]] = {
            strategy: chunks
        }
        merged_chunks = chunks

        retrieval_params = {
                "strategy": strategy,
                "top_k": top_k,
                "filter_expr": filter_expr,
                "group_by": group_by_field,
                "target_kbs": target_kbs,
                "target_docs": target_docs,
                "collections_searched": collection_names,
            }

        # =========================
        # 4️⃣ 返回
        # =========================
        return {
            "retrieval_results": retrieval_results,
            "merged_chunks": merged_chunks,
            "retrieval_params": retrieval_params,
            "processing_log": [
                {
                    "stage": "retrieval",
                    "strategy": strategy,
                    "query": query,
                    "result_count": len(chunks),
                    "collections_searched": len(collection_names),
                }
            ]
        }

    except Exception as e:
        logger.exception("[Retrieval Node] 执行失败")
        return {
            "retrieval_results": [],
            "processing_log": [
                {
                    "stage": "retrieval",
                    "error": str(e)
                }
            ]
        }


def _return_empty_results(strategy: str) -> dict:
    """返回空的检索结果"""
    return {
        "retrieval_results": {strategy: []},
        "merged_chunks": [],
        "retrieval_params": {
            "strategy": strategy,
            "top_k": 10,
            "filter_expr": None,
            "group_by": None,
            "target_kbs": [],
            "target_docs": [],
            "collections_searched": [],
        },
        "processing_log": [
            {
                "stage": "retrieval",
                "strategy": strategy,
                "result_count": 0,
                "error": "No valid collections found"
            }
        ]
    }