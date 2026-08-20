import logging
from typing import Dict, List

from dashscope import TextReRank
from config.settings import Settings
from ..state import KnowledgeAgentState

logger = logging.getLogger(__name__)
settings = Settings()

def rerank(state: KnowledgeAgentState) -> Dict:
    """
    第一次rerank：对所有filter后的chunk进行rerank

    注意：第一次rerank后不截断，保留所有chunk传递给chunk_merge节点
    最终的截断由chunk_rerank_2节点负责
    """
    settings = Settings()
    try:
        query = state.get("rewritten_query") or state["original_query"]
        chunks: List[Dict] = state.get("Light_filtered_chunks", [])

        if not chunks:
            return {"reranked_chunks": [], "processing_log": [{"stage": "rerank", "input_count": 0, "output_count": 0}]}

        # 1️⃣ 准备文本
        docs = [c["content"] for c in chunks]

        config = state.get("config", {})
        # 限制rerank数量（防止API调用过大）
        # 但设置一个较大的值，确保所有chunk都能参与rerank
        max_rerank = config.get("rerank_limit", 50)
        if len(docs) > max_rerank:
            logger.warning(f"[Rerank] chunk数量({len(docs)})超过限制({max_rerank})，截断")
            docs = docs[:max_rerank]
            chunks = chunks[:max_rerank]

        # 2️⃣ 调用 reranker
        resp = TextReRank.call(
            model=config.get("rerank_model", "qwen3-rerank"),
            query=query,
            documents=docs,
            top_n=len(docs),
            api_key=settings.dashscope_api_key,
        )

        if resp.status_code != 200:
            raise RuntimeError(resp)

        results = resp.output.results

        # 3️⃣ 写回 score
        for r in results:
            idx = r.index
            score = r.relevance_score
            chunks[idx]["rerank_score"] = score

        # 4️⃣ 排序（按rerank_score降序）
        chunks.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)

        # 5️⃣ 不截断！保留所有chunk传递给chunk_merge节点
        # 最终的截断由chunk_rerank_2节点负责

        # 打印 rerank 结果
        logger.info(f"[Rerank] 输入 {len(docs)} 个chunk, 输出 {len(chunks)} 个chunk（不截断，传递给chunk_merge）")
        for i, c in enumerate(chunks[:]):  # 只打印前10个
            score = c.get("rerank_score", 0.0)
            preview = c.get("content", "")[:60].replace('\n', ' ')
            chunk_id = c.get("chunk_id", "N/A")
            logger.info(f"  [{i+1}] rerank_score={score:.4f} | chunk_id={chunk_id} | {preview}...")

        return {
            "reranked_chunks": chunks,
            "processing_log": [
                {
                    "stage": "rerank",
                    "method": "qwen_reranker",
                    "input_count": len(docs),
                    "output_count": len(chunks),
                }
            ]
        }

    except Exception as e:
        logger.exception("[Rerank] failed")
        return {
            "reranked_chunks": state.get("Light_filtered_chunks", []),
            "processing_log": [{"stage": "rerank", "error": str(e)}]
        }