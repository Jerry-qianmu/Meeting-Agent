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

from dashscope import TextReRank
from typing import Dict, List
from ..structure_info.chunk import Chunk
from config.settings import Settings
settings = Settings()

def rerank(state: KnowledgeAgentState) -> Dict:
    settings = Settings()
    try:
        query = state.get("rewritten_query") or state["original_query"]
        chunks: List[Dict] = state.get("Light_filtered_chunks", [])

        if not chunks:
            return {"Light_filtered_chunks": []}
        # 1️⃣ 准备文本
        docs = [c["content"] for c in chunks]

        config = state.get("config", {})
        # ⚠️ 限制 rerank 数量（重要）
        max_rerank = config.get("rerank_limit", 20)
        docs = docs[:max_rerank]
        chunks = chunks[:max_rerank]

        # 2️⃣ 调用 reranker
        resp = TextReRank.call(
            model=config.get("rerank_model", "qwen3-vl-rerank"),
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

        # 4️⃣ 排序
        chunks.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)

        # 5️⃣ 截断（最终上下文）
        top_n = state.get("config", {}).get("final_top_k", 8)
        chunks = chunks[:top_n]

        return {
            "reranked_chunks":chunks,
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
            "Light_filtered_chunks": state.get("Light_filtered_chunks", []),
            "processing_log": [{"stage": "rerank", "error": str(e)}]
        }