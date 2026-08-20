# -*- coding: utf-8 -*-
"""
Memory Retrieval Node - 记忆检索注入节点（Phase 3 升级版）

使用 InterviewLibrarian 进行三通道 RRF 检索：
1. 关键词搜索（MySQL LIKE）
2. 向量相似度搜索（Milvus，如果可用）
3. 实体聚合搜索
"""

import logging
import os
import sys
from typing import Dict, Any

logger = logging.getLogger(__name__)
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.append(os.path.dirname(grand_parent_dir))

from config.settings import Settings
settings = Settings()

# Milvus 单例（避免重复连接）
_milvus_instance = None
def _get_milvus():
    global _milvus_instance
    if _milvus_instance is None:
        try:
            from database.milvus.milvus_service import MilvusService
            _milvus_instance = MilvusService()
        except Exception:
            pass
    return _milvus_instance


def memory_retrieval(state: Dict[str, Any]) -> dict:
    """
    Memory Retrieval Node

    使用 InterviewLibrarian 三通道 RRF 检索相关记忆，
    结合认知画像，注入到 generate_answer 的上下文中。
    """
    user_id = state.get("user_id")
    query = state.get("rewritten_query") or state.get("original_query", "")

    if not user_id or not query:
        return {"memory_context": ""}

    try:
        from database.mysql.mysql_client import get_db_client
        from service.memory.librarian import InterviewLibrarian

        db_client = get_db_client()
        if not db_client:
            return {"memory_context": ""}

        # 尝试获取 embedding 和 milvus 服务（可选）
        embedding_service = None
        milvus_service = None
        try:
            from service.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
        except Exception:
            pass
        milvus_service = _get_milvus()

        # 创建 Librarian 实例
        librarian = InterviewLibrarian(
            db_client=db_client,
            embedding_service=embedding_service,
            milvus_service=milvus_service,
        )

        # 三通道 RRF 检索
        search_results = librarian.search(query, user_id, top_k=8)

        # 获取认知画像
        profile_text = librarian.get_cognitive_profile(user_id)

        # 构建记忆上下文
        context_parts = []

        if profile_text:
            context_parts.append(profile_text)

        if search_results:
            memory_lines = []
            for i, result in enumerate(search_results[:5], 1):
                entity_tag = f" [{result['entity_name']}]" if result.get('entity_name') else ""
                source_tag = f"({result['source_type']})" if result['source_type'] == 'episode' else ""
                memory_lines.append(
                    f"{i}. {result['content']}{entity_tag}{source_tag}"
                )
            if memory_lines:
                context_parts.append("【相关记忆】\n" + "\n".join(memory_lines))

        memory_context = "\n\n".join(context_parts) if context_parts else ""

        if memory_context:
            logger.info(
                f"[MemoryRetrieval] 注入记忆上下文: {len(memory_context)} 字, "
                f"检索结果: {len(search_results)} 条"
            )

        return {"memory_context": memory_context}

    except Exception as e:
        logger.error(f"[MemoryRetrieval] 检索失败: {e}", exc_info=True)
        return {"memory_context": ""}
