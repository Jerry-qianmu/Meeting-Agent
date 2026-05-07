import os,sys
import os,sys
import numpy as np
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.append(os.path.dirname(grand_parent_dir))
from service.retrieval_service import get_retrieval_service
import logging
logger = logging.getLogger(__name__)
from agents.knowledge.state import KnowledgeAgentState

from typing import Dict, List
from agents.knowledge.structure_info.chunk import Chunk
from config.settings import Settings
from agents.knowledge.structure_info.chunk import ChunkSelectionResult

logger = logging.getLogger(__name__)


def cosine_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)

def diversity_selection_node(state: Dict) -> Dict:
    """
    Diversity Selection（MMR）

    输入：
    - Light_filtered_chunks（已 rerank）
    - embedding（chunk 里已有 dense 向量，或者需要补）

    输出：
    - selected_chunks
    - selection_results
    """

    try:
        chunks: List[Dict] = state.get("Light_filtered_chunks", [])
        if not chunks:
            return {
                "selected_chunks": [],
                "selection_results": []
            }

        top_k = state.get("config", {}).get("final_top_k", 5)
        lambda_param = state.get("config", {}).get("mmr_lambda", 0.7)

        # ⚠️ 要有向量（用于计算相似度）
        if "dense" not in chunks[0]:
            logger.warning("[MMR] chunk 没有向量，降级为 heuristic")
            return _fallback_selection(chunks, top_k)

        selected = []
        selected_indices = []
        results: List[ChunkSelectionResult] = []

        # 先选 rerank 第一名
        selected.append(chunks[0])
        selected_indices.append(0)

        results.append({
            "chunk_id": chunks[0]["chunk_id"],
            "selected": True,
            "selection_method": "mmr",
            "score": chunks[0].get("rerank_score"),
            "redundancy_score": 0.0,
            "reason": "top relevance",
        })

        # MMR 迭代
        while len(selected) < min(top_k, len(chunks)):
            best_score = -1
            best_idx = -1
            best_redundancy = 0

            for i, c in enumerate(chunks):
                if i in selected_indices:
                    continue

                relevance = c.get("rerank_score", 0.0)

                # 计算和已选的最大相似度（冗余）
                redundancy = max(
                    cosine_sim(c["dense"], s["dense"])
                    for s in selected
                )

                mmr_score = lambda_param * relevance - (1 - lambda_param) * redundancy

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i
                    best_redundancy = redundancy

            selected.append(chunks[best_idx])
            selected_indices.append(best_idx)

            results.append({
                "chunk_id": chunks[best_idx]["chunk_id"],
                "selected": True,
                "selection_method": "mmr",
                "score": best_score,
                "redundancy_score": best_redundancy,
                "reason": "mmr selection",
            })

        # 标记未选中的
        selected_ids = {c["chunk_id"] for c in selected}
        for c in chunks:
            if c["chunk_id"] not in selected_ids:
                results.append({
                    "chunk_id": c["chunk_id"],
                    "selected": False,
                    "selection_method": "mmr",
                    "score": c.get("rerank_score"),
                    "redundancy_score": None,
                    "reason": "not selected",
                })

        return {
            "selected_chunks": selected,
            "selection_results": results,
        }

    except Exception as e:
        logger.exception("[DiversitySelection] failed")
        return {
            "selected_chunks": [],
            "selection_results": []
        }
    
def _fallback_selection(chunks, top_k):
    selected = chunks[:top_k]

    results = []
    for i, c in enumerate(chunks):
        results.append({
            "chunk_id": c["chunk_id"],
            "selected": i < top_k,
            "selection_method": "heuristic",
            "score": c.get("rerank_score"),
            "redundancy_score": None,
            "reason": "top_k fallback",
        })

    return {
        "selected_chunks": selected,
        "selection_results": results,
    }