from typing import TypedDict, Optional, Literal ,List, Dict
from dataclasses import dataclass, field

class QualityBreakdown(TypedDict):
    relevance: float        # 回答是否针对问题
    groundedness: float     # 是否基于 context（最关键）
    completeness: float     # 是否覆盖问题
    factuality: float       # 是否逻辑正确（可选）

class QualityIssue(TypedDict):
    issue_type: Literal[
        "hallucination",
        "missing_info",
        "irrelevant",
        "low_confidence",
        "contradiction"
    ]

    severity: Literal["low", "medium", "high"]

    description: str


class QualityDecision(TypedDict):
    passed: bool

    score: float

    breakdown: QualityBreakdown

    issues: List[QualityIssue]

    # 👇 关键：驱动下一步
    should_retry: bool
    retry_reason: Optional[str]

    # fallback 独立出来
    fallback_used: bool
    fallback_reason: Optional[str]


class RetrievalRetryState(TypedDict):
    should_retry: bool

    retry_count: int
    max_retries: int

    # 👇 为什么要重试（来自 quality）
    trigger_reason: Literal[
        "hallucination",
        "missing_info",
        "irrelevant",
        "low_confidence"
    ]

    # 👇 关键：怎么改策略
    retry_strategy: Literal[
        "broaden_query",        # 扩展查询
        "narrow_query",         # 收紧查询
        "switch_retriever",     # 切换检索方式
        "increase_top_k",       # 提高召回数量
        "reweight_rerank",      # 调整排序
        "no_retry"              # 不再重试
    ]

    # 👇 可选：新 query（如果改写）
    rewritten_query: Optional[str]

    # 👇 是否已经触达终止条件
    stop_reason: Optional[str]