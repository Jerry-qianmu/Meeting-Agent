from typing import TypedDict, Optional, Literal
from dataclasses import dataclass, field
"""每一个chunk的信息"""
class Chunk(TypedDict):
    # content
    content: str

    # source infomation
    doc_id: str
    chunk_id: str
    chunk_index: int
    # document info
    url: Optional[str] = None
    page: Optional[str] = None
    section: Optional[str] = None

    # retrieval info
    method: Optional[Literal['hybrid', 'keyword', 'vector']] = None
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    hybrid_score: Optional[float] = None

"""chunk是否被过滤以及过滤原因"""
class Chunk_Filter_Decision(TypedDict):
    chunk_id: str

    # 保留 / 删除
    action: Literal["keep", "remove"]

    # 过滤原因（结构化核心）
    reason_type: Literal[
        "low_similarity",
        "duplicate",
        "too_long",
        "too_short",
        "irrelevant",
        "bad_source",
        "policy_filter",
        "other"
    ]

    # 自然语言解释（用于 debug）
    reason_text: Optional[str]

    # 过滤分数（可选）
    score: Optional[float]

    # 阈值信息（非常重要，用于调参）
    threshold: Optional[float]

"""chunk过滤统计信息"""
class Chunk_Filter_Stats(TypedDict):
    total: int
    chunk_filtered_count: int
    chunk_filtered_ratio: float



class ChunkSelectionResult(TypedDict):
    chunk_id: str

    selected: bool

    selection_method: Literal[
        "mmr",
        "heuristic"
    ]

    score: Optional[float]

    redundancy_score: Optional[float]

    reason: Optional[str]
