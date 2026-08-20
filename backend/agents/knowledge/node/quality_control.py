"""
Quality Control Node - 评估答案质量，决定是否重试检索
"""

import json
import logging
from datetime import datetime

from config.settings import Settings
from ..state import KnowledgeAgentState
from ..structure_info.quality import QualityDecision, QualityBreakdown, QualityIssue, RetrievalRetryState
from ..structure_info.RAGconfig import RAGconfig

logger = logging.getLogger(__name__)
settings = Settings()

# 质量评估系统提示词
QUALITY_EVALUATION_SYSTEM = (
    "你是一个严格的质量评估专家。评估 RAG 系统生成的答案质量。\n\n"
    "评估维度：\n"
    "1. relevance（相关性）: 答案是否针对问题（0-1）\n"
    "2. groundedness（ groundedness）: 是否基于提供的上下文材料，没有编造（0-1）\n"
    "3. completeness（完整性）: 是否覆盖了问题的所有方面（0-1）\n"
    "4. factuality（事实性）: 逻辑是否正确，没有明显错误（0-1）\n\n"
    "必须返回 JSON 格式：\n"
    "{\n"
    '  "score": 总分 (0-1),\n'
    '  "breakdown": {"relevance": x, "groundedness": x, "completeness": x, "factuality": x},\n'
    '  "issues": [{"issue_type": "hallucination|missing_info|irrelevant|low_confidence|contradiction", '
    '"severity": "low|medium|high", "description": "..."}],\n'
    '  "passed": true/false,\n'
    '  "should_retry": true/false,\n'
    '  "retry_reason": "如果重试，说明原因",\n'
    '  "fallback_used": true/false,\n'
    '  "fallback_reason": "如果使用了 fallback，说明原因"\n'
    "}\n\n"
    "通过标准：\n"
    "- 总分 >= 0.6 且 groundedness >= 0.5 且 relevance >= 0.5\n"
    "- 没有 high 严重程度的 issue\n\n"
    "不要输出 JSON 之外的任何内容。"
)


def quality_control(state: KnowledgeAgentState) -> dict:
    """
    Quality Control Node - 质量评估
    
    输入：
    - generation_output: GenerationOutput
    - original_query: str
    - retrieval_retry: RetrievalRetryState (可选，当前重试次数)
    
    输出：
    - quality_decision: QualityDecision
    - retrieval_retry: 更新后的重试状态
    """
    logger.info("Quality Control Node - 质量评估")
    start_time = datetime.now()
    
    try:
        # 1️⃣ 获取输入
        generation_output = state.get("generation_output")
        if not generation_output:
            logger.warning("[QualityControl] 没有 generation_output")
            return _create_fallback_response(state.get("original_query", ""))
        
        query = state.get("rewritten_query") or state.get("original_query", "")
        answer = generation_output.get("answer", "")
        metadata = generation_output.get("metadata", {})
        citations = generation_output.get("citations", [])
        
        # 2️⃣ 获取配置
        config = state.get("config", {})
        if isinstance(config, RAGconfig):
            config = _ragconfig_to_dict(config)
        
        # 3️⃣ 获取当前重试状态
        retrieval_retry = state.get("retrieval_retry") or _create_initial_retry_state(config)
        retry_count = retrieval_retry.get("retry_count", 0)
        max_retries = retrieval_retry.get("max_retries", config.get("quality_max_retries", 2))
        
        # 4️⃣ 快速规则评估（低成本）
        rule_based_decision = _rule_based_quality_check(
            query, answer, metadata, citations, retrieval_retry, config
        )
        
        # 5️⃣ 如果规则评估通过，直接返回
        if rule_based_decision["passed"]:
            logger.info(f"[QualityControl] 规则评估通过 (score={rule_based_decision['score']})")
            duration = (datetime.now() - start_time).total_seconds() * 1000
            return {
                "quality_decision": rule_based_decision,
                "retrieval_retry": retrieval_retry,
                "processing_log": [
                    {
                        "stage": "quality_control",
                        "duration_ms": duration,
                        "method": "rule_based",
                        "passed": True,
                        "score": rule_based_decision["score"]
                    }
                ]
            }
        
        # 6️⃣ 如果达到最大重试次数，强制返回 fallback
        if retry_count >= max_retries:
            logger.warning(f"[QualityControl] 达到最大重试次数 ({max_retries})，返回 fallback")
            return _create_fallback_response(query, rule_based_decision)
        
        # 7️⃣ LLM 质量评估（高成本，仅在规则评估不通过时调用）
        llm_decision = _llm_quality_evaluation(
            query, answer, metadata, citations, config
        )
        
        # 8️⃣ 合并规则评估和 LLM 评估
        final_decision = _merge_decisions(rule_based_decision, llm_decision)
        
        # 9️⃣ 决定是否重试
        if not final_decision["passed"] and retry_count < max_retries:
            # 确定重试策略
            retry_strategy = _determine_retry_strategy(final_decision, retrieval_retry)
            
            # 更新重试状态
            retrieval_retry = {
                "should_retry": True,
                "retry_count": retry_count + 1,
                "max_retries": max_retries,
                "trigger_reason": final_decision["issues"][0]["issue_type"] if final_decision["issues"] else "low_confidence",
                "retry_strategy": retry_strategy,
                "rewritten_query": None,  # 可以在这里生成新的 query
                "stop_reason": None
            }
            
            logger.info(
                f"[QualityControl] 质量不达标，触发重试 "
                f"(count={retry_count + 1}/{max_retries}, strategy={retry_strategy})"
            )
        else:
            retrieval_retry = {
                **retrieval_retry,
                "should_retry": False,
                "stop_reason": "quality_passed" if final_decision["passed"] else "max_retries_reached"
            }
        
        # 计算耗时
        duration = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(
            f"[QualityControl] 完成 ({duration:.0f}ms): "
            f"score={final_decision['score']:.2f}, passed={final_decision['passed']}"
        )
        
        return {
            "quality_decision": final_decision,
            "retrieval_retry": retrieval_retry,
            "processing_log": [
                {
                    "stage": "quality_control",
                    "duration_ms": duration,
                    "method": "rule_based + llm" if not rule_based_decision["passed"] else "rule_based",
                    "passed": final_decision["passed"],
                    "score": final_decision["score"],
                    "retry_count": retrieval_retry["retry_count"],
                    "retry_strategy": retrieval_retry.get("retry_strategy")
                }
            ]
        }
    
    except Exception as e:
        logger.exception("[QualityControl] 执行失败")
        safe_config = state.get("config", {}) if isinstance(state, dict) else {}
        return {
            "quality_decision": _create_error_response(),
            "retrieval_retry": state.get("retrieval_retry") or _create_initial_retry_state(safe_config),
            "processing_log": [
                {
                    "stage": "quality_control",
                    "error": str(e)
                }
            ]
        }


def _rule_based_quality_check(
    query: str, 
    answer: str, 
    metadata: dict, 
    citations: list,
    retrieval_retry: dict,
    config: dict
) -> QualityDecision:
    """
    基于规则的质量检查（低成本）
    使用 RAGconfig 中的阈值配置
    """
    issues = []
    
    # 从 config 获取阈值
    score_threshold = config.get("quality_score_threshold", 0.6)
    groundedness_threshold = config.get("quality_groundedness_threshold", 0.5)
    relevance_threshold = config.get("quality_relevance_threshold", 0.5)
    
    # 检查是否已经是 fallback 回答（使用通用知识）
    reasoning_type = metadata.get("reasoning_type", "")
    is_fallback_answer = reasoning_type == "general_knowledge"
    
    # 1️⃣ 检查答案长度
    answer_len = len(answer)
    if answer_len < 20 and not is_fallback_answer:
        issues.append({
            "issue_type": "missing_info",
            "severity": "high",
            "description": f"答案过短 ({answer_len} 字符)，可能信息不足"
        })
    
    # 2️⃣ 检查是否有来源引用（fallback 回答不需要引用）
    has_citations = len(citations) > 0
    if not has_citations and answer_len > 50 and not is_fallback_answer:
        issues.append({
            "issue_type": "low_confidence",
            "severity": "medium",
            "description": "答案没有引用来源"
        })
    
    # 3️⃣ 检查 metadata 中的标志
    missing_info = metadata.get("missing_info", False)
    grounded = metadata.get("grounded", True)
    
    # Fallback 回答不视为 missing_info 或 hallucination
    if missing_info and not is_fallback_answer:
        issues.append({
            "issue_type": "missing_info",
            "severity": "high",
            "description": "系统标记为信息不足"
        })
    
    if not grounded and not is_fallback_answer:
        issues.append({
            "issue_type": "hallucination",
            "severity": "high",
            "description": "系统标记为可能幻觉"
        })
    
    # 4️⃣ 检查是否有特定关键词（fallback 回答允许使用）
    if not is_fallback_answer:
        if "无法" in answer or "不能" in answer or "找不到" in answer:
            if "无法" in answer or "找不到" in answer:
                issues.append({
                    "issue_type": "missing_info",
                    "severity": "medium",
                    "description": "答案明确表示无法回答"
                })
    
    # 计算分数
    if is_fallback_answer:
        # Fallback 回答：低分，不自动通过，标记为低质量
        base_score = 0.3
        relevance = 0.5
        groundedness = 0.2  # 无知识库依据
        completeness = 0.3
        factuality = 0.4
    else:
        # 正常 RAG 回答
        base_score = 0.7
        
        # 根据问题调整分数
        if answer_len < 20:
            base_score -= 0.3
        elif answer_len < 50:
            base_score -= 0.1
        
        if not has_citations:
            base_score -= 0.1
        
        if missing_info:
            base_score -= 0.4
        
        if not grounded:
            base_score -= 0.4
        
        relevance = 0.8 if answer_len > 20 else 0.4
        groundedness = 0.9 if grounded and has_citations else 0.4
        completeness = 0.7 if answer_len > 50 else 0.4
        factuality = 0.85
        
        # 根据问题调整
        if missing_info:
            groundedness = 0.3
            completeness = 0.3
    
    # 根据重试次数调整（重试后应该提高标准）
    retry_count = retrieval_retry.get("retry_count", 0)
    if retry_count > 0:
        base_score = min(1.0, base_score + 0.1)  # 重试后稍微宽容
    
    score = max(0.0, min(1.0, base_score))
    
    breakdown: QualityBreakdown = {
        "relevance": round(relevance, 2),
        "groundedness": round(groundedness, 2),
        "completeness": round(completeness, 2),
        "factuality": round(factuality, 2)
    }
    
    # 判断是否通过（使用 config 中的阈值）
    if is_fallback_answer:
        # Fallback 回答不自动通过，但也不重试（重试不会改善）
        passed = False
        should_retry = False
    else:
        passed = (
            score >= score_threshold and 
            groundedness >= groundedness_threshold and 
            relevance >= relevance_threshold and
            not any(i["severity"] == "high" for i in issues)
        )
        should_retry = not passed and not missing_info  # 信息不足时重试可能也没用
    
    fallback_used = missing_info or not grounded or is_fallback_answer
    fallback_reason = "使用通用知识回答" if is_fallback_answer else ("信息不足" if missing_info else "可能幻觉" if not grounded else None)
    
    return {
        "passed": passed,
        "score": round(score, 2),
        "breakdown": breakdown,
        "issues": issues,
        "should_retry": should_retry,
        "retry_reason": issues[0]["description"] if issues else None,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason
    }


def _llm_quality_evaluation(
    query: str, 
    answer: str, 
    metadata: dict, 
    citations: list,
    config: dict
) -> dict:
    """
    使用 LLM 进行质量评估（高成本）
    """
    try:
        # 构建评估 prompt
        context_preview = ""
        if citations:
            context_preview = "\n".join([
                f"[{c['doc_id']}]: {c['span'][:100]}..." 
                for c in citations[:3]
            ])
        
        user_prompt = (
            f"用户问题：{query}\n\n"
            f"生成的答案：{answer}\n\n"
            f"引用来源：\n{context_preview}\n\n"
            f"请评估答案质量，返回 JSON 格式。"
        )
        
        messages = [
            {"role": "system", "content": QUALITY_EVALUATION_SYSTEM},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用 LLM（使用 config 中的模型配置）
        llm_model = config.get("quality_eval_model", settings.quality_eval_model)
        from service.llm_client import llm_call
        cfg = settings.get_llm_config("quality_eval", model=llm_model)
        result = llm_call(
            messages=messages,
            model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"], base_url=cfg["base_url"],
            temperature=0.1,
        )

        if result["status_code"] != 200:
            logger.error(f"[QualityControl] LLM 评估失败 {result['status_code']}")
            return _create_default_decision()
        
        # 解析 JSON
        try:
            content = result["content"]
            # 提取 JSON（可能有额外文本）
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                llm_result = json.loads(json_str)
            else:
                llm_result = _create_default_decision()
        except (json.JSONDecodeError, KeyError, IndexError, AttributeError) as e:
            logger.warning(f"[QualityControl] JSON 解析失败：{e}")
            llm_result = _create_default_decision()
        
        return llm_result
    
    except Exception as e:
        logger.exception("[QualityControl] LLM 评估异常")
        return _create_default_decision()


def _merge_decisions(rule_decision: dict, llm_decision: dict) -> QualityDecision:
    """
    合并规则评估和 LLM 评估结果
    """
    # 分数加权（规则 40% + LLM 60%）
    rule_score = rule_decision.get("score", 0.5)
    llm_score = llm_decision.get("score", 0.5)
    final_score = round(rule_score * 0.4 + llm_score * 0.6, 2)
    
    # 合并 breakdown（取 LLM 的，如果可用）
    final_breakdown = llm_decision.get("breakdown", rule_decision.get("breakdown", {}))
    
    # 合并 issues
    all_issues = rule_decision.get("issues", []) + llm_decision.get("issues", [])
    # 去重（按 description）
    seen = set()
    unique_issues = []
    for issue in all_issues:
        desc = issue.get("description", "")
        if desc and desc not in seen:
            seen.add(desc)
            unique_issues.append(issue)
    
    # 判断是否通过（更严格：任一评估不通过则不通过）
    rule_passed = rule_decision.get("passed", False)
    llm_passed = llm_decision.get("passed", False)
    final_passed = rule_passed and llm_passed
    
    # 合并重试决策
    rule_should_retry = rule_decision.get("should_retry", False)
    llm_should_retry = llm_decision.get("should_retry", False)
    final_should_retry = rule_should_retry or llm_should_retry
    
    # 合并 fallback
    fallback_used = rule_decision.get("fallback_used", False) or llm_decision.get("fallback_used", False)
    fallback_reason = rule_decision.get("fallback_reason") or llm_decision.get("fallback_reason")
    
    # 合并 retry_reason
    retry_reason = rule_decision.get("retry_reason") or llm_decision.get("retry_reason")
    
    return {
        "passed": final_passed,
        "score": final_score,
        "breakdown": final_breakdown,
        "issues": unique_issues,
        "should_retry": final_should_retry,
        "retry_reason": retry_reason,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason
    }


def _determine_retry_strategy(
    quality_decision: QualityDecision,
    current_retry: RetrievalRetryState
) -> str:
    """
    根据质量问题确定重试策略
    """
    issues = quality_decision.get("issues", [])
    breakdown = quality_decision.get("breakdown", {})
    
    # 根据问题类型决定策略
    for issue in issues:
        issue_type = issue.get("issue_type", "")
        if issue_type == "hallucination":
            return "narrow_query"  # 收紧查询，减少幻觉
        elif issue_type == "missing_info":
            return "broaden_query"  # 扩展查询，增加信息
        elif issue_type == "irrelevant":
            return "switch_retriever"  # 切换检索方式
        elif issue_type == "low_confidence":
            return "increase_top_k"  # 增加召回数量
    
    # 根据 breakdown 决定
    if breakdown.get("groundedness", 1) < 0.5:
        return "narrow_query"
    elif breakdown.get("completeness", 1) < 0.5:
        return "broaden_query"
    elif breakdown.get("relevance", 1) < 0.5:
        return "switch_retriever"
    
    return "no_retry"


def _create_initial_retry_state(config: dict = None) -> RetrievalRetryState:
    """创建初始重试状态"""
    if config is None:
        config = {}
    
    return {
        "should_retry": False,
        "retry_count": 0,
        "max_retries": config.get("quality_max_retries", 2),
        "trigger_reason": "no_retry",
        "retry_strategy": "no_retry",
        "rewritten_query": None,
        "stop_reason": None
    }


def _create_default_decision() -> QualityDecision:
    """创建默认评估结果"""
    return {
        "passed": False,
        "score": 0.5,
        "breakdown": {
            "relevance": 0.5,
            "groundedness": 0.5,
            "completeness": 0.5,
            "factuality": 0.5
        },
        "issues": [],
        "should_retry": True,
        "retry_reason": "默认评估失败",
        "fallback_used": False,
        "fallback_reason": None
    }


def _create_error_response() -> QualityDecision:
    """创建错误响应"""
    return {
        "passed": False,
        "score": 0.0,
        "breakdown": {
            "relevance": 0.0,
            "groundedness": 0.0,
            "completeness": 0.0,
            "factuality": 0.0
        },
        "issues": [{
            "issue_type": "error",
            "severity": "high",
            "description": "质量评估过程中发生错误"
        }],
        "should_retry": False,
        "retry_reason": "评估错误",
        "fallback_used": True,
        "fallback_reason": "评估失败"
    }


def _create_fallback_response(query: str, previous_decision: dict = None) -> dict:
    """创建 fallback 响应"""
    return {
        "quality_decision": {
            "passed": True,
            "score": 0.5,
            "breakdown": {
                "relevance": 0.5,
                "groundedness": 0.5,
                "completeness": 0.5,
                "factuality": 0.5
            },
            "issues": [],
            "should_retry": False,
            "retry_reason": None,
            "fallback_used": True,
            "fallback_reason": "质量评估失败，返回 fallback"
        },
        "retrieval_retry": {
            "should_retry": False,
            "retry_count": 0,
            "max_retries": 0,
            "trigger_reason": "fallback",
            "retry_strategy": "no_retry",
            "rewritten_query": None,
            "stop_reason": "quality_control_fallback"
        },
        "processing_log": [
            {
                "stage": "quality_control",
                "status": "fallback",
                "query": query
            }
        ]
    }


def _ragconfig_to_dict(config: RAGconfig) -> dict:
    """将 RAGconfig 对象转换为字典"""
    if hasattr(config, "__dict__"):
        return config.__dict__
    return {}
