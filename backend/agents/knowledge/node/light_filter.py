import os,sys
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.append(os.path.dirname(grand_parent_dir))
sys.path.append(os.path.dirname(parent_dir))
import logging
sys.path.append(os.path.dirname(parent_dir))
from ..state import KnowledgeAgentState
from config.settings import Settings
settings = Settings()

import logging
from typing import Dict, List

from ..structure_info.chunk import Chunk_Filter_Stats,Chunk

logger = logging.getLogger(__name__)


def light_filter(state: KnowledgeAgentState) -> Dict:
    """
    Light Filtering Layer

    输入：
    - merged_chunks: List[Chunk]

    输出：
    - Light_filtered_chunks
    - filter_stats
    """

    try:
        chunks = state.get("merged_chunks", [])

        if not chunks:
            return {
                "Light_filtered_chunks": [],
                "filter_stats": {
                    "total": 0,
                    "chunk_filtered_count": 0,
                    "chunk_filtered_ratio": 0.0,
                },
            }

        total = len(chunks)

        # =========================================================
        # 1️⃣ 去重（chunk_id）
        # =========================================================
        seen = set()
        deduped = []
        for c in chunks:
            cid = c.get("chunk_id")
            if cid and cid not in seen:
                deduped.append(c)
                seen.add(cid)

        # =========================================================
        # 2️⃣ 轻量 score filter（避免误杀，阈值要低）
        # =========================================================
        filtered = []
        for c in deduped:
            score = (
                c.get("hybrid_score")
                or c.get("vector_score")
                or c.get("keyword_score")
                or 0.0
            )
            theshold = settings.light_filter_threshold
            # ⚠️ 轻过滤阈值（建议 0.1~0.2）
            if score >= theshold:
                filtered.append(c)


        # =========================================================
        # 4️⃣ stats
        # =========================================================
        filtered_count = total - len(filtered)

        filter_stats: Chunk_Filter_Stats = {
            "total": total,
            "chunk_filtered_count": filtered_count,
            "chunk_filtered_ratio": round(filtered_count / total, 4) if total else 0.0,
        }

        logger.info(
            f"[LightFilter] total={total}, kept={len(filtered)}, "
            f"filtered={filtered_count}, ratio={filter_stats['chunk_filtered_ratio']}"
        )

        # =========================================================
        # 5️⃣ return
        # =========================================================
        return {
            "Light_filtered_chunks": filtered,
            "filter_stats": filter_stats,
        }

    except Exception as e:
        logger.exception("[LightFilter] failed")
        return {
            "Light_filtered_chunks": [],
            "filter_stats": {
                "total": 0,
                "chunk_filtered_count": 0,
                "chunk_filtered_ratio": 0.0,
            },
        }