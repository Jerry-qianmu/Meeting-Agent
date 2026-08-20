from typing import TypedDict, Optional, Literal ,List, Dict
from dataclasses import dataclass, field

class ContextBlock(TypedDict):
    chunk_id: str
    doc_id: str
    text: str
    token_count: int
    score: float


class ContextPack(TypedDict):
    blocks: List[ContextBlock]
    total_tokens: int
    compressed_text: str
    compression_ratio: float


"""可追溯检索索引"""
class Citation(TypedDict):
    chunk_id: str
    doc_id: str
    span: Optional[str] # 对应的证据信息
    confidence: float


class AnswerMetadata(TypedDict):
    confidence: float            # 整体置信度

    reasoning_type: Literal[
        "direct",        # 单 chunk
        "multi_hop",     # 多 chunk 推理
        "synthesis"      # 综合总结
    ]

    grounded: bool               # 是否完全基于 context
    missing_info: bool           # 是否信息不足


class GenerationOutput(TypedDict):
    answer: str
    metadata: AnswerMetadata
    citations: List[Citation]
    follow_up_questions: List[str]