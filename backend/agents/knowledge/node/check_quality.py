"""
Check Quality Node - 质量评估决策节点（路由）
调用 quality_control 进行评估，并根据结果决定流向
"""

import logging
from datetime import datetime

from ..state import KnowledgeAgentState
from .quality_control import quality_control

logger = logging.getLogger(__name__)


def check_quality(state: KnowledgeAgentState) -> dict:
    """
    Check Quality Node - 质量检查与路由
    
    输入：
    - generation_output: GenerationOutput
    - original_query: str
    
    输出：
    - quality_decision: QualityDecision
    - retrieval_retry: RetrievalRetryState
    
    路由逻辑：
    - quality_decision.passed == True → 返回最终答案
    - quality_decision.should_retry == True → 回到检索流程
    - quality_decision.fallback_used == True → 返回 fallback 答案
    """
    logger.info("Check Quality Node - 质量检查与路由")
    start_time = datetime.now()
    
    try:
        # 1️⃣ 调用 quality_control 进行评估
        quality_result = quality_control(state)
        
        quality_decision = quality_result.get("quality_decision", {})
        retrieval_retry = quality_result.get("retrieval_retry", {})
        
        # 2️⃣ 提取关键决策信息
        passed = quality_decision.get("passed", False)
        should_retry = quality_decision.get("should_retry", False)
        fallback_used = quality_decision.get("fallback_used", False)
        
        score = quality_decision.get("score", 0.0)
        fallback_reason = quality_decision.get("fallback_reason")
        retry_reason = quality_decision.get("retry_reason")
        
        # 3️⃣ 记录决策日志
        logger.info(
            f"[CheckQuality] 决策：passed={passed}, should_retry={should_retry}, "
            f"fallback_used={fallback_used}, score={score:.2f}"
        )
        
        # 4️⃣ 返回结果（供路由节点使用）
        duration = (datetime.now() - start_time).total_seconds() * 1000
        
        return {
            "quality_decision": quality_decision,
            "retrieval_retry": retrieval_retry,
            "processing_log": [
                {
                    "stage": "check_quality",
                    "duration_ms": duration,
                    "passed": passed,
                    "should_retry": should_retry,
                    "fallback_used": fallback_used,
                    "score": score,
                    "retry_reason": retry_reason,
                    "fallback_reason": fallback_reason
                }
            ]
        }
    
    except Exception as e:
        logger.exception("[CheckQuality] 执行失败")
        return {
            "quality_decision": {
                "passed": False,
                "score": 0.0,
                "breakdown": {"relevance": 0.0, "groundedness": 0.0, "completeness": 0.0, "factuality": 0.0},
                "issues": [{"issue_type": "system_error", "severity": "high", "description": f"质量评估系统错误：{e}"}],
                "should_retry": False,
                "retry_reason": "系统错误",
                "fallback_used": True,
                "fallback_reason": "质量评估系统错误"
            },
            "retrieval_retry": {
                "should_retry": False,
                "retry_count": 999,
                "max_retries": 2,
                "trigger_reason": "system_error",
                "retry_strategy": "no_retry",
                "rewritten_query": None,
                "stop_reason": "system_error"
            },
            "processing_log": [
                {
                    "stage": "check_quality",
                    "error": str(e)
                }
            ]
        }
