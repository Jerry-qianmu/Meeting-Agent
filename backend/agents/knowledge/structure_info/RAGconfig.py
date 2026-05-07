from typing_extensions import TypedDict
from typing import List, Dict, Any, Optional, Annotated
from dataclasses import dataclass, field
import os,sys
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.append(os.path.dirname(grand_parent_dir))

from config.settings import Settings
settings = Settings()

@dataclass
class RAGconfig:
    """RAG pipeline configuration"""
    # Model settings
    rewrite_model: str = settings.rewrite_model
    determine_retrieval_strategy_model: str =  settings.determine_retrieval_strategy_model

    top_k: int = settings.top_k
    filter_expr: Optional[str] = settings.filter_expr

    # keyword
    use_text_match_filter: bool = settings.use_text_match_filter
    keyword_filter: Optional[str] = settings.keyword_filter

    # hybrid
    ranker: str = settings.ranker
    rrf_k: int = settings.rrf_k
    hybrid_alpha: float = settings.hybrid_alpha

    # group
    group_by_field: Optional[str] = settings.group_by_field
    group_size: int =  settings.group_size
    strict_group_size: bool = settings.strict_group_size
    
    # light filter
    light_filter_threshold: float = settings.light_filter_threshold

    # rerank
    rerank_model: str = settings.rerank_model
    rerank_limit: int = settings.rerank_limit
    rerank_final_top_k: int = settings.rerank_final_top_k

   # generation
    generation_model: str = settings.generation_model
    max_context_tokens: int = settings.max_context_tokens
    
    # quality control
    quality_eval_model: str = settings.quality_eval_model
    quality_max_retries: int = settings.quality_max_retries
    
    # 质量通过阈值
    quality_score_threshold: float = settings.quality_score_threshold
    quality_groundedness_threshold: float = settings.quality_groundedness_threshold
    quality_relevance_threshold: float = settings.quality_relevance_threshold
    
    # 重试策略参数
    retry_broaden_threshold_delta: float = settings.retry_broaden_threshold_delta
    retry_broaden_topk_delta: int = settings.retry_broaden_topk_delta
    retry_narrow_threshold_delta: float = settings.retry_narrow_threshold_delta
    retry_narrow_topk_delta: int = settings.retry_narrow_topk_delta
    retry_increase_topk_delta: int = settings.retry_increase_topk_delta
    


    