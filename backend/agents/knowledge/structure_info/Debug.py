from typing import TypedDict, Optional, Literal ,List, Dict, Any
from dataclasses import dataclass, field

class TraceInfo(TypedDict):
    trace_id: str
    session_id: Optional[str]
    user_id: Optional[str]

class Metrics(TypedDict):
    total_latency_ms: float

    # 分阶段耗时
    stage_latency: Dict[str, float]

    # 检索指标
    retrieved_chunks: int
    filtered_chunks: int
    final_chunks: int

    # token 使用
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    # retry
    retry_count: int


class LogEntry(TypedDict):
    stage: str              # 哪个阶段
    action: str             # 做了什么
    message: str
    timestamp: float
    data: Optional[Dict[str, Any]]  # 关键上下文（小规模）

class WarningEntry(TypedDict):
    stage: str
    message: str


class ErrorEntry(TypedDict):
    stage: str
    error_type: str
    message: str
    details: Optional[Dict[str, Any]]

class DebugInfo(TypedDict):
    query_rewrite: Optional[Dict[str, Any]]
    retrieval: Optional[Dict[str, Any]]
    rerank: Optional[Dict[str, Any]]
    generation: Optional[Dict[str, Any]]
    quality: Optional[Dict[str, Any]]

class Observability(TypedDict):
    trace: TraceInfo
    metrics: Metrics

    logs: List[LogEntry]

    warnings: List[WarningEntry]
    errors: List[ErrorEntry]

    debug: DebugInfo