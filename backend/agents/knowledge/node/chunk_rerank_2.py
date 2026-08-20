# -*- coding: utf-8 -*-
"""
Chunk Rerank 2 Node
对合并后的chunks进行第二次rerank，确保最终返回高质量的chunks
"""

import logging
from typing import Dict, List
from dashscope import TextReRank
from ..state import KnowledgeAgentState
from config.settings import Settings

logger = logging.getLogger(__name__)


def chunk_rerank_2(state: KnowledgeAgentState) -> Dict:
    """
    第二次rerank，对合并后的chunks进行重新排序

    输入：chunk_merged_chunks（合并后的chunks）
    输出：reranked_chunks（最终排序的chunks）

    核心逻辑：
    1. 检查是否启用第二次rerank
    2. 调用reranker模型重新评分
    3. 按新分数排序
    4. 截断到最终top_k
    """

    query = state.get("rewritten_query") or state["original_query"]
    chunks = state.get("chunk_merged_chunks", [])
    config = state.get("config", {})
    settings = Settings()

    if not chunks:
        return {"reranked_chunks": []}

    # 从config读取配置（支持per-request覆盖），fallback到Settings
    chunk_merge_enable_second_rerank = getattr(config, "chunk_merge_enable_second_rerank", settings.chunk_merge_enable_second_rerank)

    # 检查是否启用第二次rerank
    if not chunk_merge_enable_second_rerank:
        logger.info("[ChunkRerank2] 第二次rerank已禁用，直接返回合并后的chunks")
        return {"reranked_chunks": chunks}

    try:
        # 准备文本
        docs = [c["content"] for c in chunks]

        # 限制rerank数量
        chunk_merge_second_rerank_limit = getattr(config, "chunk_merge_second_rerank_limit", settings.chunk_merge_second_rerank_limit)
        max_rerank = chunk_merge_second_rerank_limit
        if len(docs) > max_rerank:
            logger.info(f"[ChunkRerank2] 截断chunks: {len(docs)} -> {max_rerank}")
            docs = docs[:max_rerank]
            chunks = chunks[:max_rerank]

        # 调用reranker
        resp = TextReRank.call(
            model=settings.rerank_model,
            query=query,
            documents=docs,
            top_n=len(docs),
            api_key=settings.dashscope_api_key,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Rerank API error: {resp}")

        results = resp.output.results

        # 写回第二次rerank的score
        for r in results:
            idx = r.index
            score = r.relevance_score
            chunks[idx]["rerank_score_2"] = score

        # 排序（优先使用第二次rerank分数）
        chunks.sort(
            key=lambda x: x.get("rerank_score_2", x.get("rerank_score", 0.0)),
            reverse=True
        )

        # 截断到最终top_k
        chunk_merge_final_top_k = getattr(config, "chunk_merge_final_top_k", settings.chunk_merge_final_top_k)
        final_top_k = chunk_merge_final_top_k
        final_chunks = chunks[:final_top_k]

        # 打印rerank结果
        logger.info(f"[ChunkRerank2] 输入 {len(docs)} 个chunk, 输出 {len(final_chunks)} 个chunk")
        for i, c in enumerate(final_chunks[:]):
            score = c.get("rerank_score_2", c.get("rerank_score", 0.0))
            preview = c.get("content", "")[:60].replace('\n', ' ')
            # 显示merged来源或原始chunk_id
            merged_from = c.get("merged_from", [])
            expanded_from = c.get("expanded_from", [])
            if merged_from:
                chunk_id = f"merged[{','.join([cid[:8] for cid in merged_from])}]"
            elif expanded_from:
                chunk_id = f"expanded[{','.join([cid[:8] for cid in expanded_from])}]"
            else:
                chunk_id = c.get("chunk_id", "N/A")[:12]
            logger.info(f"  [{i+1}] score={score:.4f} | chunk_id={chunk_id} | {preview}...")

        return {
            "reranked_chunks": final_chunks,
            "processing_log": [
                {
                    "stage": "chunk_rerank_2",
                    "method": "qwen_reranker",
                    "input_count": len(docs),
                    "output_count": len(final_chunks),
                }
            ]
        }

    except Exception as e:
        logger.exception("[ChunkRerank2] failed")
        # 失败时返回原始合并后的chunks（按第一次rerank分数排序）
        chunks.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        chunk_merge_final_top_k = getattr(config, "chunk_merge_final_top_k", settings.chunk_merge_final_top_k)
        return {
            "reranked_chunks": chunks[:chunk_merge_final_top_k],
            "processing_log": [{"stage": "chunk_rerank_2", "error": str(e)}]
        }
