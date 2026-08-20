import hashlib
import logging
from typing import Dict, List

from ..state import KnowledgeAgentState
from ..structure_info.chunk import Chunk_Filter_Stats
from config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()

MIN_CONTENT_LENGTH = 10


def _content_hash(text: str) -> str:
    normalized = text.strip().replace('\n', '').replace(' ', '')
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()


def light_filter(state: KnowledgeAgentState) -> Dict:
    """
    Light Filtering Layer
    1. chunk_id 去重  2. 内容 hash 去重  3. 最小长度  4. score 过滤
    失败时 fail-open：透传原数据
    """
    try:
        chunks = state.get("merged_chunks", [])
        if not chunks:
            return {
                "Light_filtered_chunks": [],
                "filter_stats": {"total": 0, "chunk_filtered_count": 0, "chunk_filtered_ratio": 0.0},
            }

        total = len(chunks)

        # 1. chunk_id 去重
        seen_ids = set()
        deduped = []
        for c in chunks:
            cid = c.get("chunk_id")
            if cid and cid not in seen_ids:
                deduped.append(c)
                seen_ids.add(cid)

        # 2. 内容 hash 去重
        seen_hashes = set()
        content_deduped = []
        for c in deduped:
            h = _content_hash(c.get("content", ""))
            if h not in seen_hashes:
                content_deduped.append(c)
                seen_hashes.add(h)

        # 3. 最小内容长度
        length_filtered = [c for c in content_deduped if len(c.get("content", "").strip()) >= MIN_CONTENT_LENGTH]

        # 4. score 过滤
        threshold = settings.light_filter_threshold
        filtered = []
        for c in length_filtered:
            score = c.get("hybrid_score") or c.get("vector_score") or c.get("keyword_score") or 0.0
            if score >= threshold:
                filtered.append(c)

        # score 过滤后为空但之前有数据 → 降级
        if not filtered and length_filtered:
            logger.warning("[LightFilter] score 过滤后为空，降级为跳过 score 过滤")
            filtered = length_filtered

        filtered_count = total - len(filtered)
        filter_stats: Chunk_Filter_Stats = {
            "total": total,
            "chunk_filtered_count": filtered_count,
            "chunk_filtered_ratio": round(filtered_count / total, 4) if total else 0.0,
        }

        logger.info(f"[LightFilter] total={total}, kept={len(filtered)}, filtered={filtered_count}")
        return {"Light_filtered_chunks": filtered, "filter_stats": filter_stats}

    except Exception as e:
        # Fail-open
        logger.exception("[LightFilter] failed, fail-open")
        return {
            "Light_filtered_chunks": state.get("merged_chunks", []),
            "filter_stats": {"total": 0, "chunk_filtered_count": 0, "chunk_filtered_ratio": 0.0},
        }