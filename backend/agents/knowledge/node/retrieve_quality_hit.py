"""
Retrieve Quality Hit Node - 质量驱动的重试检索节点
根据质量评估结果，决定是否重试检索以及如何重试
"""

import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional

cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.append(os.path.dirname(parent_dir))

from ..state import KnowledgeAgentState
from ..structure_info.RAGconfig import RAGconfig
from config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()


def retrieve_quality_hit(state: KnowledgeAgentState) -> dict:
    """
    Retrieve Quality Hit Node - 质量驱动的重试检索
    
    输入：
    - quality_decision: QualityDecision
    - retrieval_retry: RetrievalRetryState
    - original_query: str
    - rewritten_query: Optional[str]
    - config: RAGconfig
    
    输出：
    - 如果不需要重试：返回最终答案
    - 如果需要重试：返回更新后的状态，回到检索流程
    
    路由逻辑：
    - quality_decision.passed == True → 返回最终答案 (return_final_answer)
    - quality_decision.should_retry == True → 重试检索 (retrieval)
    - quality_decision.fallback_used == True → 返回 fallback 答案
    """
    logger.info("Retrieve Quality Hit Node - 质量驱动的重试检索")
    start_time = datetime.now()
    
    try:
        # 1️⃣ 获取决策信息
        quality_decision = state.get("quality_decision", {})
        retrieval_retry = state.get("retrieval_retry", {})
        
        passed = quality_decision.get("passed", False)
        should_retry = quality_decision.get("should_retry", False)
        fallback_used = quality_decision.get("fallback_used", False)
        
        retry_count = retrieval_retry.get("retry_count", 0)
        max_retries = retrieval_retry.get("max_retries", 2)
        retry_strategy = retrieval_retry.get("retry_strategy", "no_retry")
        trigger_reason = retrieval_retry.get("trigger_reason", "unknown")
        
        logger.info(
            f"[RetrieveQualityHit] passed={passed}, should_retry={should_retry}, "
            f"fallback_used={fallback_used}, retry_count={retry_count}/{max_retries}, "
            f"strategy={retry_strategy}"
        )
        
        # 2️⃣ 判断是否需要重试
        if passed and not fallback_used:
            # 质量达标，返回最终答案
            logger.info("[RetrieveQualityHit] 质量达标，返回最终答案")
            return _return_final_answer(state)
        
        elif fallback_used:
            # 已使用 fallback，不再重试
            logger.info("[RetrieveQualityHit] 已使用 fallback，返回 fallback 答案")
            return _return_fallback_answer(state)
        
        elif should_retry and retry_count < max_retries:
            # 需要重试且未达最大次数
            logger.info(
                f"[RetrieveQualityHit] 触发重试 (count={retry_count}/{max_retries}, "
                f"strategy={retry_strategy}, reason={trigger_reason})"
            )
            return _retry_retrieval(state, retry_strategy, trigger_reason)
        
        elif should_retry and retry_count >= max_retries:
            # 达到最大重试次数
            logger.warning(f"[RetrieveQualityHit] 达到最大重试次数 ({max_retries})，返回 fallback")
            return _return_fallback_answer(state, "达到最大重试次数")
        
        else:
            # 默认返回当前答案
            logger.info("[RetrieveQualityHit] 无重试需求，返回当前答案")
            return _return_final_answer(state)
    
    except Exception as e:
        logger.exception("[RetrieveQualityHit] 执行失败")
        return {
            "error": str(e),
            "processing_log": [
                {
                    "stage": "retrieve_quality_hit",
                    "error": str(e)
                }
            ]
        }


def _return_final_answer(state: KnowledgeAgentState) -> dict:
    """返回最终答案"""
    generation_output = state.get("generation_output", {})
    quality_decision = state.get("quality_decision", {})
    sources = state.get("sources", [])
    context_pack = state.get("context_pack", {})
    
    return {
        "final_answer": generation_output.get("answer", ""),
        "final_metadata": generation_output.get("metadata", {}),
        "final_citations": generation_output.get("citations", []),
        "follow_up_questions": generation_output.get("follow_up_questions", []),
        "sources": sources,
        "context_pack": context_pack,
        "quality_decision": quality_decision,
        "retrieval_retry": state.get("retrieval_retry", {}),
        "processing_log": [
            {
                "stage": "retrieve_quality_hit",
                "action": "return_final_answer",
                "quality_passed": True,
                "score": quality_decision.get("score", 0.0)
            }
        ]
    }


def _return_fallback_answer(state: KnowledgeAgentState, reason: Optional[str] = None) -> dict:
    """返回 fallback 答案"""
    original_query = state.get("original_query", "")
    quality_decision = state.get("quality_decision", {})
    
    # 优先使用 generate_answer 中已经生成的 fallback 答案（通用知识回答）
    generation_output = state.get("generation_output", {})
    existing_answer = generation_output.get("answer", "")
    
    if existing_answer:
        # 已经有生成的答案，使用它
        fallback_answer = existing_answer
        fallback_metadata = generation_output.get("metadata", {})
        fallback_citations = generation_output.get("citations", [])
        follow_up_questions = generation_output.get("follow_up_questions", [])
        logger.info(f"[RetrieveQualityHit] 使用已生成的 fallback 答案 ({len(existing_answer)} 字符)")
    else:
        # 没有生成答案，使用硬编码的 fallback
        fallback_reason = reason or quality_decision.get("fallback_reason", "信息不足")
        fallback_answer = (
            f"抱歉，经过多次检索和评估，知识库中未能找到足够的信息来完整回答您的问题。\n\n"
            f"原因：{fallback_reason}\n\n"
            f"建议您：\n"
            f"1. 尝试用不同的关键词重新提问\n"
            f"2. 补充更多具体信息\n"
            f"3. 联系相关人员获取帮助"
        )
        fallback_metadata = {
            "confidence": 0.0,
            "reasoning_type": "direct",
            "grounded": False,
            "missing_info": True
        }
        fallback_citations = []
        follow_up_questions = []
    
    sources = state.get("sources", [])
    context_pack = state.get("context_pack", {})
    
    return {
        "final_answer": fallback_answer,
        "final_metadata": fallback_metadata,
        "final_citations": fallback_citations,
        "follow_up_questions": follow_up_questions,
        "sources": sources,
        "context_pack": context_pack,
        "quality_decision": quality_decision,
        "retrieval_retry": state.get("retrieval_retry", {}),
        "processing_log": [
            {
                "stage": "retrieve_quality_hit",
                "action": "return_fallback_answer",
                "fallback_reason": reason or quality_decision.get("fallback_reason"),
                "answer_length": len(fallback_answer)
            }
        ]
    }


def _retry_retrieval(
    state: KnowledgeAgentState, 
    retry_strategy: str, 
    trigger_reason: str
) -> dict:
    """
    执行重试检索
    
    根据 retry_strategy 调整检索参数：
    - broaden_query: 扩展查询（降低相似度阈值，增加 top_k）
    - narrow_query: 收紧查询（提高相似度阈值，减少 top_k）
    - switch_retriever: 切换检索方式（vector <-> keyword <-> hybrid）
    - increase_top_k: 增加召回数量
    - reweight_rerank: 调整 rerank 参数
    """
    try:
        # 1️⃣ 获取当前配置
        config = state.get("config", {})
        if isinstance(config, RAGconfig):
            config = _ragconfig_to_dict(config)
        config = config.copy()
        
        original_query = state.get("original_query", "")
        rewritten_query = state.get("rewritten_query", original_query)
        
        # 2️⃣ 根据策略调整参数（使用 RAGconfig 中的配置）
        new_config = _adjust_retrieval_params(config, retry_strategy, trigger_reason)
        
        # 3️⃣ 可能需要改写 query
        new_query = _maybe_rewrite_query(rewritten_query, retry_strategy, trigger_reason)
        
        # 4️⃣ 构建新的状态，准备回到检索流程
        retrieval_retry = state.get("retrieval_retry", {})
        
        return {
            # 重置检索相关状态（保留查询和配置）
            "original_query": original_query,
            "rewritten_query": new_query,
            "config": new_config,
            
            # 清空需要重新生成的状态
            "retrieval_results": [],
            "merged_chunks": [],
            "Light_filtered_chunks": [],
            "reranked_chunks": [],
            "context_pack": {},
            "generation_output": {},
            "sources": [],
            
            # 保留重试状态
            "retrieval_retry": {
                **retrieval_retry,
                "retry_count": retrieval_retry.get("retry_count", 0) + 1,
                "retry_strategy": retry_strategy,
                "trigger_reason": trigger_reason
            },
            
            "processing_log": [
                {
                    "stage": "retrieve_quality_hit",
                    "action": "retry_retrieval",
                    "retry_count": retrieval_retry.get("retry_count", 0) + 1,
                    "retry_strategy": retry_strategy,
                    "trigger_reason": trigger_reason,
                    "params_changed": _get_changed_params(config, new_config)
                }
            ]
        }
    
    except Exception as e:
        logger.exception("[RetryRetrieval] 重试失败")
        # 重试失败，返回 fallback
        return _return_fallback_answer(state, f"重试检索失败：{e}")


def _adjust_retrieval_params(
    config: Dict[str, Any], 
    retry_strategy: str,
    trigger_reason: str
) -> Dict[str, Any]:
    """
    根据重试策略调整检索参数
    使用 RAGconfig 中的配置参数
    """
    new_config = config.copy()
    
    if retry_strategy == "broaden_query":
        # 扩展查询：降低阈值，增加召回
        threshold_delta = config.get("retry_broaden_threshold_delta", -0.05)
        topk_delta = config.get("retry_broaden_topk_delta", 5)
        
        current_threshold = config.get("similarity_threshold", config.get("light_filter_threshold", 0.15))
        current_topk = config.get("top_k", 10)
        
        new_config["similarity_threshold"] = current_threshold + threshold_delta
        new_config["top_k"] = current_topk + topk_delta
        new_config["rerank_limit"] = config.get("rerank_limit", 20) + topk_delta
        new_config["rerank_final_top_k"] = config.get("rerank_final_top_k", 8) + 2
        
    elif retry_strategy == "narrow_query":
        # 收紧查询：提高阈值，减少噪声
        threshold_delta = config.get("retry_narrow_threshold_delta", 0.1)
        topk_delta = config.get("retry_narrow_topk_delta", -3)
        
        current_threshold = config.get("similarity_threshold", config.get("light_filter_threshold", 0.15))
        current_topk = config.get("top_k", 10)
        
        new_config["similarity_threshold"] = current_threshold + threshold_delta
        new_config["top_k"] = max(5, current_topk + topk_delta)
        new_config["rerank_limit"] = max(10, config.get("rerank_limit", 20) + topk_delta)
        
    elif retry_strategy == "switch_retriever":
        # 切换检索方式
        current_strategy = config.get("retrieval_strategy", "hybrid")
        if current_strategy == "hybrid":
            new_config["retrieval_strategy"] = "vector"
        elif current_strategy == "vector":
            new_config["retrieval_strategy"] = "keyword"
        else:
            new_config["retrieval_strategy"] = "hybrid"
        
    elif retry_strategy == "increase_top_k":
        # 增加召回数量
        topk_delta = config.get("retry_increase_topk_delta", 5)
        new_config["top_k"] = config.get("top_k", 10) + topk_delta
        new_config["rerank_limit"] = config.get("rerank_limit", 20) + topk_delta
        
    elif retry_strategy == "reweight_rerank":
        # 调整 rerank 权重
        new_config["hybrid_alpha"] = 0.8  # 更重视向量分数
        
    # 确保参数在合理范围内
    new_config["similarity_threshold"] = max(0.05, min(0.5, new_config.get("similarity_threshold", 0.15)))
    new_config["top_k"] = max(5, min(50, new_config.get("top_k", 10)))
    new_config["rerank_limit"] = max(10, min(50, new_config.get("rerank_limit", 20)))
    new_config["rerank_final_top_k"] = max(3, min(15, new_config.get("rerank_final_top_k", 8)))
    
    return new_config


def _maybe_rewrite_query(
    current_query: str,
    retry_strategy: str,
    trigger_reason: str
) -> str:
    """
    根据重试策略调用 LLM 改写 query
    """
    from dashscope import Generation

    strategy_hints = {
        "broaden_query": "请将以下问题扩展为更宽泛、包含更多同义词和相关概念的版本，保留原意但增加召回面：",
        "narrow_query": "请将以下问题缩小范围、增加限定条件，使其更精确、减少歧义：",
        "switch_retriever": "请将以下问题改写为更适合关键词检索的版本（使用关键术语、去掉口语化表达）：",
        "increase_top_k": "请将以下问题用不同的措辞重新表达，保持原意：",
        "reweight_rerank": "请将以下问题改写为更精确、更聚焦核心概念的版本：",
    }

    hint = strategy_hints.get(retry_strategy, "请将以下问题用不同的措辞重新表达：")

    prompt = (
        f"{hint}\n\n"
        f"原始问题：{current_query}\n"
        f"重试原因：{trigger_reason}\n\n"
        f"只输出改写后的问题，不要输出其他内容。"
    )

    try:
        from service.llm_client import llm_call
        cfg = settings.get_llm_config("rewrite")
        result = llm_call(
            messages=[
                {"role": "system", "content": "你是一个搜索查询改写专家。只输出改写后的问题。"},
                {"role": "user", "content": prompt},
            ],
            model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"], base_url=cfg["base_url"],
        )
        if result["status_code"] == 200:
            rewritten = (result["content"] or "").strip()
            if rewritten and len(rewritten) > 2:
                logger.info(f"[QueryRewrite] {retry_strategy}: {current_query} → {rewritten}")
                return rewritten
    except Exception as e:
        logger.warning(f"[QueryRewrite] 改写失败: {e}")

    return current_query


def _get_changed_params(
    old_config: Dict[str, Any], 
    new_config: Dict[str, Any]
) -> Dict[str, Any]:
    """获取变化的参数"""
    changed = {}
    for key in new_config:
        if old_config.get(key) != new_config.get(key):
            changed[key] = {
                "old": old_config.get(key),
                "new": new_config.get(key)
            }
    return changed


def _ragconfig_to_dict(config: RAGconfig) -> Dict[str, Any]:
    """将 RAGconfig 对象转换为字典"""
    if isinstance(config, dict):
        return config
    
    return {
        "rewrite_model": getattr(config, "rewrite_model", "qwen3.5-plus"),
        "determine_retrieval_strategy_model": getattr(config, "determine_retrieval_strategy_model", "qwen3.5-plus"),
        "top_k": getattr(config, "top_k", 10),
        "filter_expr": getattr(config, "filter_expr", ""),
        "use_text_match_filter": getattr(config, "use_text_match_filter", False),
        "keyword_filter": getattr(config, "keyword_filter", ""),
        "ranker": getattr(config, "ranker", "RRF"),
        "rrf_k": getattr(config, "rrf_k", 60),
        "hybrid_alpha": getattr(config, "hybrid_alpha", 0.7),
        "group_by_field": getattr(config, "group_by_field", ""),
        "group_size": getattr(config, "group_size", 5),
        "strict_group_size": getattr(config, "strict_group_size", False),
        "light_filter_threshold": getattr(config, "light_filter_threshold", 0.15),
        "rerank_model": getattr(config, "rerank_model", "qwen3-vl-rerank"),
        "rerank_limit": getattr(config, "rerank_limit", 20),
        "rerank_final_top_k": getattr(config, "rerank_final_top_k", 8),
        "generation_model": getattr(config, "generation_model", "qwen3.5-plus"),
        "max_context_tokens": getattr(config, "max_context_tokens", 4096),
        # quality control
        "quality_eval_model": getattr(config, "quality_eval_model", "qwen3.5-plus"),
        "quality_max_retries": getattr(config, "quality_max_retries", 2),
        "quality_score_threshold": getattr(config, "quality_score_threshold", 0.6),
        "quality_groundedness_threshold": getattr(config, "quality_groundedness_threshold", 0.5),
        "quality_relevance_threshold": getattr(config, "quality_relevance_threshold", 0.5),
        "retry_broaden_threshold_delta": getattr(config, "retry_broaden_threshold_delta", -0.05),
        "retry_broaden_topk_delta": getattr(config, "retry_broaden_topk_delta", 5),
        "retry_narrow_threshold_delta": getattr(config, "retry_narrow_threshold_delta", 0.1),
        "retry_narrow_topk_delta": getattr(config, "retry_narrow_topk_delta", -3),
        "retry_increase_topk_delta": getattr(config, "retry_increase_topk_delta", 5),
    }
