"""
Generate Answer Node - 基于检索到的 chunks 生成最终答案
"""

import os
import sys
import logging
from datetime import datetime

cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.append(os.path.dirname(grand_parent_dir))
sys.path.append(os.path.dirname(parent_dir))

from dashscope import Generation
from config.settings import Settings
from ..state import KnowledgeAgentState
from ..structure_info.context import ContextPack, ContextBlock, GenerationOutput, AnswerMetadata, Citation

logger = logging.getLogger(__name__)
settings = Settings()

from ..prompt.generate_answer import GENERATE_ANSWER_SYSTEM


def build_context_pack(chunks: list, max_tokens: int = 4000) -> ContextPack:
    """
    构建上下文包
    
    Args:
        chunks: 排序后的 chunks
        max_tokens: 最大 token 数
    
    Returns:
        ContextPack
    """
    blocks = []
    total_tokens = 0
    compressed_parts = []
    
    for chunk in chunks:
        content = chunk.get("content", "")
        # 估算 token 数（粗略：1 汉字≈1.5 token，1 英文单词≈1 token）
        char_count = len(content)
        token_count = int(char_count * 1.2)  # 保守估计
        
        if total_tokens + token_count > max_tokens:
            break
        
        blocks.append({
            "chunk_id": chunk.get("chunk_id", ""),
            "doc_id": chunk.get("doc_id", ""),
            "text": content,
            "token_count": token_count,
            "score": chunk.get("rerank_score") or chunk.get("hybrid_score") or 0.0
        })
        
        compressed_parts.append(f"[{chunk.get('doc_id', '')}]\n{content}")
        total_tokens += token_count
    
    compressed_text = "\n\n---\n\n".join(compressed_parts)
    compression_ratio = len(compressed_text) / total_tokens if total_tokens > 0 else 0
    
    return {
        "blocks": blocks,
        "total_tokens": total_tokens,
        "compressed_text": compressed_text,
        "compression_ratio": compression_ratio
    }


def generate_answer(state: KnowledgeAgentState) -> dict:
    """
    Generate Answer Node - 答案生成
    
    输入：
    - reranked_chunks: List[Chunk] (已排序的 chunks)
    - original_query: str
    - rewritten_query: Optional[str]
    
    输出：
    - generation_output: GenerationOutput
    - context_pack: ContextPack
    - sources: List[Dict]
    """
    logger.info("Generate Answer Node - 答案生成")
    start_time = datetime.now()
    
    try:
        # 1️⃣ 获取输入
        query = state.get("rewritten_query") or state["original_query"]
        chunks = state.get("reranked_chunks", [])
        history_prompt = state.get("history_prompt", "") or ""
        history_messages = state.get("history_messages", [])
        
        if not chunks:
            logger.warning("[GenerateAnswer] 没有检索结果，使用模型自身知识回答")
            return _create_fallback_response(query, history_prompt, history_messages)
        
        # 2️⃣ 构建上下文包
        config = state.get("config", {})
        max_tokens = config.get("max_context_tokens", 4000)
        context_pack = build_context_pack(chunks, max_tokens)
        
        logger.info(
            f"[GenerateAnswer] context: {len(context_pack['blocks'])} blocks, "
            f"{context_pack['total_tokens']} tokens"
        )
        
        # 3️⃣ 构建 prompt（含历史记忆）
        history_section = ""
        if history_prompt:
            history_section = f"\n\n【历史对话摘要】\n{history_prompt}"
        elif history_messages:
            # history_prompt 为空时，用缓冲区原始对话
            history_lines = []
            for msg in history_messages:
                if hasattr(msg, "type"):
                    if msg.type == "human":
                        history_lines.append(f"用户：{msg.content}")
                    elif msg.type == "ai":
                        history_lines.append(f"助手：{msg.content or ''}")
            if history_lines:
                history_section = "\n\n【近期对话】\n" + "\n".join(history_lines)

        user_prompt = (
            f"用户问题：{query}\n"
            f"{history_section}\n"
            f"上下文材料：\n{context_pack['compressed_text']}\n\n"
            f"请根据以上材料回答问题："
        )
        
        messages = [
            {"role": "system", "content": GENERATE_ANSWER_SYSTEM},
            {"role": "user", "content": user_prompt}
        ]
        
        # 4️⃣ 调用 LLM 生成答案
        model = config.get("generate_model", settings.generation_model)
        response = Generation.call(
            api_key=settings.dashscope_api_key,
            model=model,
            messages=messages,
            result_format="message"
        )
        
        if response.status_code != 200:
            logger.error(f"[GenerateAnswer] LLM error {response.status_code}: {response}")
            return _create_fallback_response(query, history_prompt, history_messages)
        
        # 5️⃣ 解析答案
        try:
            answer = (
                response.output.choices[0].message.get("content") or ""
            ).strip()
        except (KeyError, IndexError, AttributeError):
            answer = ""
        
        if not answer:
            logger.warning("[GenerateAnswer] LLM 返回空答案，使用备用回答")
            return _create_fallback_response(query, history_prompt, history_messages)
        
        # 6️⃣ 构建 citations（可追溯来源）
        citations = []
        for i, block in enumerate(context_pack["blocks"]):
            if i < 5:  # 最多引用前 5 个来源
                citations.append({
                    "chunk_id": block["chunk_id"],
                    "doc_id": block["doc_id"],
                    "span": block["text"][:200],  # 截取前 200 字符作为证据
                    "confidence": block["score"]
                })
        
        # 7️⃣ 构建 metadata
        confidence = _calculate_confidence(chunks)
        grounded = _check_groundedness(answer, context_pack["compressed_text"])
        
        metadata: AnswerMetadata = {
            "confidence": confidence,
            "reasoning_type": "synthesis" if len(chunks) > 1 else "direct",
            "grounded": grounded,
            "missing_info": not grounded
        }
        
        # 8️⃣ 生成后续问题建议
        follow_up_questions = _generate_follow_ups(query, answer)
        
        # 9️⃣ 构建输出
        generation_output: GenerationOutput = {
            "answer": answer,
            "metadata": metadata,
            "citations": citations,
            "follow_up_questions": follow_up_questions
        }
        
        # 🔟 构建 sources（用于前端展示）
        sources = [
            {
                "doc_id": block["doc_id"],
                "chunk_id": block["chunk_id"],
                "score": block["score"],
                "preview": block["text"][:300]
            }
            for block in context_pack["blocks"][:5]
        ]
        
        # 计算耗时
        duration = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"[GenerateAnswer] 完成 ({duration:.0f}ms): {len(answer)} 字符")
        
        return {
            "generation_output": generation_output,
            "context_pack": context_pack,
            "sources": sources,
            "processing_log": [
                {
                    "stage": "generate_answer",
                    "duration_ms": duration,
                    "query": query,
                    "answer_length": len(answer),
                    "context_blocks": len(context_pack["blocks"]),
                    "context_tokens": context_pack["total_tokens"],
                    "model": model
                }
            ]
        }
    
    except Exception as e:
        logger.exception("[GenerateAnswer] 执行失败")
        return {
            "generation_output": _create_fallback_response(state.get("original_query", ""))["generation_output"],
            "processing_log": [
                {
                    "stage": "generate_answer",
                    "error": str(e)
                }
            ]
        }


def _create_fallback_response(query: str, history_prompt: str = "", 
                               history_messages: list = None) -> dict:
    """
    创建备用响应 - 使用模型自身知识回答
    当没有检索结果或检索结果质量差时使用
    """
    if history_messages is None:
        history_messages = []

    logger.info(f"[GenerateAnswer] 使用模型自身知识回答：{query}")

    # 构建历史上下文：优先用 history_prompt（压缩），否则用 history_messages（缓冲区）
    history_section = ""
    if history_prompt:
        history_section = f"\n\n【历史对话摘要】\n{history_prompt}"
    elif history_messages:
        # 将缓冲区转为对话格式
        history_lines = []
        for msg in history_messages:
            if hasattr(msg, "type"):
                if msg.type == "human":
                    history_lines.append(f"用户：{msg.content}")
                elif msg.type == "ai":
                    history_lines.append(f"助手：{msg.content or ''}")
        if history_lines:
            history_section = "\n\n【近期对话】\n" + "\n".join(history_lines)

    # 调用 LLM 使用自身知识回答
    try:
        messages = [
            {
                "role": "system", 
                "content": "你是一个智能助手。请根据对话历史和你的知识来回答用户的问题。如果对话历史中包含相关信息，请优先使用。请用中文回答。"
            },
            {
                "role": "user", 
                "content": f"用户问题：{query}{history_section}\n\n请回答："
            }
        ]
        
        response = Generation.call(
            api_key=settings.dashscope_api_key,
            model=settings.generation_model,
            messages=messages,
            result_format="message",
            timeout=60  # 延长超时到 60 秒
        )
        
        logger.info(f"[GenerateAnswer] Fallback API 响应：status={response.status_code}")
        
        if response.status_code == 200:
            try:
                answer = (
                    response.output.choices[0].message.get("content") or 
                    "抱歉，我无法回答这个问题。"
                ).strip()
                logger.info(f"[GenerateAnswer] Fallback 答案长度：{len(answer)} 字符")
            except (KeyError, IndexError, AttributeError) as e:
                logger.error(f"[GenerateAnswer] 解析 Fallback 响应失败：{e}")
                answer = "抱歉，我无法回答这个问题。"
        else:
            # 如果 API 也失败，返回简单的默认回答
            logger.error(f"[GenerateAnswer] Fallback API 调用失败：{response.code} - {response.message}")
            answer = (
                f"抱歉，目前没有找到相关的参考资料。"
                f"关于这个问题 \"{query}\"，我无法提供准确的信息。"
            )
    except Exception as e:
        logger.error(f"[GenerateAnswer] Fallback API 调用失败：{e}")
        answer = (
            f"抱歉，目前没有找到相关的参考资料。"
            f"关于这个问题 \"{query}\"，我无法提供准确的信息。"
        )
    
    return {
        "generation_output": {
            "answer": answer,
            "metadata": {
                "confidence": 0.5,  # 中等置信度，因为是通用知识
                "reasoning_type": "general_knowledge",
                "grounded": False,
                "missing_info": False  # 不算是信息不足，而是使用通用知识
            },
            "citations": [],
            "follow_up_questions": _generate_follow_ups(query, answer)
        },
        "context_pack": {
            "blocks": [],
            "total_tokens": 0,
            "compressed_text": "",
            "compression_ratio": 0.0
        },
        "sources": [],
        "processing_log": [
            {
                "stage": "generate_answer",
                "status": "fallback_general_knowledge",
                "query": query,
                "answer_length": len(answer)
            }
        ]
    }


def _calculate_confidence(chunks: list) -> float:
    """
    计算答案置信度
    基于检索结果的分数和数量
    """
    if not chunks:
        return 0.0
    
    # 使用 rerank_score 或 hybrid_score
    scores = [
        chunk.get("rerank_score") or chunk.get("hybrid_score") or chunk.get("vector_score") or 0.0
        for chunk in chunks[:5]  # 只看前 5 个
    ]
    
    if not scores:
        return 0.0
    
    avg_score = sum(scores) / len(scores)
    
    # 分数映射到置信度（0-1）
    # 假设 rerank_score 范围 0-1
    confidence = min(1.0, max(0.0, avg_score))
    
    # 根据结果数量调整
    if len(chunks) == 1:
        confidence *= 0.8  # 单一来源，降低置信度
    elif len(chunks) >= 3:
        confidence *= 1.1  # 多来源佐证，提高置信度
    
    return round(min(1.0, confidence), 2)


def _check_groundedness(answer: str, context_text: str) -> bool:
    """
    检查答案是否基于上下文
    简单启发式：检查答案中是否包含上下文中的关键词
    """
    if not answer or not context_text:
        return False
    
    # 简单检查：如果答案很短但上下文很长，可能是编造
    if len(answer) < 20 and len(context_text) > 1000:
        return False
    
    # 检查答案中是否包含来源标注
    if "[doc_id:" in answer or "[文档" in answer:
        return True
    
    # 检查是否承认信息不足
    if "无法" in answer or "没有" in answer or "不足" in answer:
        return True
    
    return True  # 默认认为基于上下文


def _generate_follow_ups(query: str, answer: str) -> list:
    """
    生成后续问题建议
    """
    # 简单启发式：基于问题类型生成
    follow_ups = []
    
    if "怎么" in query or "如何" in query:
        follow_ups.append(f"{query} 的具体步骤是什么？")
        follow_ups.append(f"{query} 有哪些注意事项？")
    elif "是什么" in query or "什么是" in query:
        follow_ups.append(f"{query} 的应用场景有哪些？")
        follow_ups.append(f"{query} 和类似概念有什么区别？")
    elif "为什么" in query:
        follow_ups.append(f"{query} 的反例是什么？")
        follow_ups.append(f"{query} 的历史背景是什么？")
    else:
        follow_ups.append(f"关于这个问题，还有什么需要了解的？")
        follow_ups.append(f"这个问题相关的扩展知识有哪些？")
    
    return follow_ups[:3]  # 最多 3 个
