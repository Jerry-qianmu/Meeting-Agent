# -*- coding: utf-8 -*-
"""
Generate Answer Node - 基于检索到的 chunks 生成最终答案
v2: 支持 MCP tool-calling (web_search)
"""

import json
import logging
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from config.settings import Settings
from ..state import KnowledgeAgentState
from ..structure_info.context import ContextPack, ContextBlock, GenerationOutput, AnswerMetadata, Citation
from service.tokenizer import count_tokens

logger = logging.getLogger(__name__)
settings = Settings()

from ..prompt.generate_answer import GENERATE_ANSWER_SYSTEM


# ── Prompt Templates ──────────────────────────────────────────────────────────

TOOL_CALLING_SYSTEM = """你是一个智能助手，可以访问知识库和互联网搜索来回答问题。

## 可用工具
{tool_descriptions}

## 工作流程
1. 如果知识库中有相关信息，直接基于知识库回答
2. 如果知识库中没有相关信息（context 为空），可以使用 web_search 工具搜索互联网
3. 搜索到结果后，基于搜索结果为用户提供准确的答案
4. 请在答案中标注信息来源

## 回答要求
- 用中文回答
- 准确、简洁、有依据
- 如果使用了搜索，标注"（来源：互联网搜索）"
- 不要编造信息"""


# ── Main Node ─────────────────────────────────────────────────────────────────

def generate_answer(state: KnowledgeAgentState) -> dict:
    """
    Generate Answer Node - 支持 MCP tool-calling

    ReAct 流程：
    1. 首次进入：构建 prompt + 检索上下文 → 调用 LLM
       - 如果 web_search_enabled 且无检索结果 → 带 tools 调用，LLM 可能返回 tool_calls
       - 如果有检索结果 → 正常生成
    2. ReAct 回环（execute_tool 后再次进入）：
       - 检测到最后一条消息是 ToolMessage
       - 用完整对话历史（含工具交互）再次调用 LLM 得到最终答案
    """
    logger.info("[GenerateAnswer] 答案生成")
    start_time = datetime.now()

    messages = state.get("messages", [])

    # ── 检测是否是 ReAct 回环（execute_tool 后重新进入） ──
    if _detect_react_reentry(messages):
        logger.info("[GenerateAnswer] 检测到 ReAct 回环，基于工具结果生成最终答案")
        return _generate_after_tool_call(state, start_time)

    # ── 首次进入：正常流程 ──
    query = state.get("rewritten_query") or state["original_query"]
    chunks = state.get("reranked_chunks", [])
    history_prompt = state.get("history_prompt", "") or ""
    history_messages = state.get("history_messages", [])
    web_search_enabled = state.get("web_search_enabled", False)
    config = state.get("config", {})
    memory_context = state.get("memory_context", "") or ""
    sub_queries = state.get("sub_queries") or []

    # 构建历史上下文
    history_section = _build_history_section(history_prompt, history_messages)

    # ── 路径 A: 有检索结果 → 正常 KB 回答 ──
    if chunks:
        return _generate_with_context(query, chunks, history_section, config, start_time, memory_context, sub_queries)

    # ── 路径 B: 无检索结果 + 联网搜索开启 → tool-calling ──
    if web_search_enabled:
        # 提前检查 MCP 是否可用
        from service.MCP.mcp_tool_registry import get_mcp_registry_sync
        registry = get_mcp_registry_sync()
        if registry and registry.is_initialized and registry.tool_count > 0:
            return _generate_with_tools(query, history_section, state, start_time, memory_context)
        else:
            reason = (
                "MCP 注册表未初始化" if not registry
                else "MCP 未完成初始化" if not registry.is_initialized
                else "没有可用工具"
            )
            logger.warning(f"[GenerateAnswer] 联网搜索已开启但 {reason}，降级为 fallback")

    # ── 路径 C: 无检索结果 + 联网搜索关闭 → fallback ──
    logger.warning("[GenerateAnswer] 没有检索结果，使用模型自身知识回答")
    return _create_fallback_response(query, history_prompt, history_messages, memory_context)


# ── ReAct Re-entry Detection ──────────────────────────────────────────────────

def _detect_react_reentry(messages: list) -> bool:
    """检测是否是从 execute_tool 回环重新进入"""
    if len(messages) < 2:
        return False
    last_msg = messages[-1]
    # ToolMessage 表示刚执行完工具
    if isinstance(last_msg, ToolMessage):
        return True
    # 或者检测是否有 AIMessage(tool_calls) 已执行
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, ToolMessage):
            return True
        if isinstance(msg, HumanMessage):
            break
    return False


# ── Path A: KB Context Answer ─────────────────────────────────────────────────

def _generate_with_context(
    query: str, chunks: list, history_section: str, config: dict,
    start_time: datetime, memory_context: str = "", sub_queries: list = None
) -> dict:
    """路径 A：基于检索到的 chunks 生成答案（现有逻辑）"""
    max_tokens = config.get("max_context_tokens", 4096)
    context_pack = build_context_pack(chunks, max_tokens)

    logger.info(
        f"[GenerateAnswer] context: {len(context_pack['blocks'])} blocks, "
        f"{context_pack['total_tokens']} tokens"
    )
    for i, blk in enumerate(context_pack["blocks"]):
        preview = blk["text"][:100].replace("\n", " ")
        logger.info(f"  [context {i+1}] doc_id={blk['doc_id']} | score={blk['score']:.4f} | {preview}...")

    # 构建记忆上下文部分（来自 Memory Constellations）
    memory_section = ""
    if memory_context:
        memory_section = f"\n{memory_context}\n"

    # 构建回答指引
    if sub_queries:
        # 有子查询：引导 LLM 逐子查询回答
        sub_query_guide = "\n".join(f"  {i+1}. {sq}" for i, sq in enumerate(sub_queries))
        answer_guide = (
            f"回答要求（必须严格遵守）：\n"
            f"1. 请逐一回答以下子问题，每个子问题的答案必须从上下文片段中提取：\n"
            f"{sub_query_guide}\n"
            f"2. 每个子问题的回答必须完整，不要遗漏任何信息\n"
            f"3. 最后将所有子问题的答案整合为一个完整的回答\n"
            f"4. 只使用上下文中的信息，不要编造\n"
        )
    else:
        # 无子查询：使用通用指引
        import re as _re
        entities = _re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', query)
        entity_checklist = ""
        if len(entities) >= 2:
            entity_checklist = (
                f"\n⚠️ 实体检查清单（必须逐一在上下文中查找以下实体）：\n"
                + "\n".join(f"  □ {e}" for e in entities)
                + "\n"
            )
        answer_guide = (
            f"回答要求（必须严格遵守）：\n"
            f"1. 逐一检查每个片段，查找问题中提到的每个实体的信息\n"
            f"2. 如果涉及多个实体，必须从所有片段中分别提取每个实体的信息\n"
            f"3. 只有确认所有片段中都不包含某实体的信息时，才能说\"未找到\"\n"
            f"4. 只使用上下文中的信息，不要编造\n"
        )

    user_prompt = (
        f"用户问题：{query}\n"
        f"{history_section}\n"
        f"{memory_section}\n"
        f"{answer_guide}\n"
        f"上下文材料（共 {len(context_pack['blocks'])} 个片段）：\n"
        f"{context_pack['compressed_text']}\n\n"
        f"请基于上述片段回答："
    )

    # ── 调试：打印完整 user_prompt 以确认上下文内容 ──
    logger.info(f"[GenerateAnswer] === USER PROMPT START ===")
    logger.info(user_prompt[:3000])
    if len(user_prompt) > 3000:
        logger.info(f"... (truncated, total {len(user_prompt)} chars)")
    logger.info(f"[GenerateAnswer] === USER PROMPT END ===")

    messages = [
        {"role": "system", "content": GENERATE_ANSWER_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]

    model = config.get("generate_model", settings.generation_model)
    answer = _call_llm(model, messages)

    # ── 自检轮：检查是否有信息遗漏，如有则补充 ──
    if answer and context_pack['compressed_text']:
        answer = _self_check_and_supplement(
            model, query, answer, context_pack['compressed_text'], sub_queries
        )

    if not answer:
        logger.warning("[GenerateAnswer] LLM 返回空答案，使用备用回答")
        return _create_fallback_response(query, config.get("history_prompt", ""),
                                         config.get("history_messages", []))

    # 构建 citations 和 metadata
    citations = _build_citations(context_pack["blocks"])
    metadata = _build_metadata(chunks, answer, context_pack["compressed_text"])
    follow_up_questions = _generate_follow_ups(query, answer)
    sources = _build_sources(context_pack["blocks"])

    generation_output: GenerationOutput = {
        "answer": answer,
        "metadata": metadata,
        "citations": citations,
        "follow_up_questions": follow_up_questions,
    }

    duration = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(f"[GenerateAnswer] KB回答完成 ({duration:.0f}ms): {len(answer)} 字符")

    return {
        "generation_output": generation_output,
        "context_pack": context_pack,
        "web_search_used": False,
        "sources": sources,
        "processing_log": [{
            "stage": "generate_answer",
            "duration_ms": duration,
            "query": query,
            "answer_length": len(answer),
            "context_blocks": len(context_pack["blocks"]),
            "context_tokens": context_pack["total_tokens"],
            "model": model,
        }],
    }


# ── Path B: Tool-Calling (web_search) ─────────────────────────────────────────

def _generate_with_tools(
    query: str, history_section: str, state: dict, start_time: datetime,
    memory_context: str = ""
) -> dict:
    """路径 B：带 web_search 工具的 LLM 调用"""
    from service.MCP.mcp_tool_registry import get_mcp_registry_sync

    registry = get_mcp_registry_sync()
    # 注意：调用方已确保 registry 可用，这里只是二次确认
    if not registry or not registry.is_initialized or registry.tool_count == 0:
        logger.error("[GenerateAnswer] _generate_with_tools 被调用时 MCP 不可用（不应发生）")
        return _create_fallback_response(
            query, state.get("history_prompt", ""), state.get("history_messages", [])
        )

    config = state.get("config", {})
    model = config.get("generate_model", settings.generation_model)
    tool_schemas = registry.get_tool_schemas()
    tool_names = registry.get_tool_names()
    tool_descriptions = _format_tool_descriptions(registry)

    # 检查是否已经调用过工具（tool_call_count > 0）
    tool_call_count = state.get("tool_call_count", 0)
    max_tool_calls = state.get("max_tool_calls", 5)

    logger.info(
        f"[GenerateAnswer] Tool-calling 模式: "
        f"{len(tool_schemas)} 工具, 已调用 {tool_call_count}/{max_tool_calls} 次"
    )

    # 构建 messages
    system_content = TOOL_CALLING_SYSTEM.format(tool_descriptions=tool_descriptions)

    # 检查消息历史中是否有之前的工具交互（多轮 tool-calling）
    messages_for_llm = _build_tool_calling_messages(
        system_content, query, history_section, state, tool_call_count
    )

    # 调用 LLM with tools
    try:
        from service.llm_client import llm_call
        cfg = settings.get_llm_config("generation", model=model)
        result = llm_call(
            messages=messages_for_llm,
            model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"], base_url=cfg["base_url"],
            tools=tool_schemas if tool_call_count < max_tool_calls else None,
            timeout=60,
        )

        logger.info(f"[GenerateAnswer] Tool-calling API: status={result['status_code']}")

        if result["status_code"] != 200:
            logger.error(f"[GenerateAnswer] LLM error: status={result['status_code']}")
            return _create_fallback_response(
                query, state.get("history_prompt", ""), state.get("history_messages", [])
            )

        content = result["content"]
        tool_calls_raw = result["tool_calls"]

        # 检查是否有 tool_calls
        if tool_calls_raw and tool_call_count < max_tool_calls:
            tool_calls = tool_calls_raw
            logger.info(
                f"[GenerateAnswer] LLM 请求工具调用: "
                f"{[tc.get('function', {}).get('name', '?') for tc in tool_calls]}"
            )

            # 转换为 LangChain AIMessage 格式
            lc_tool_calls = []
            for tc in tool_calls:
                func = tc.get("function", {})
                lc_tool_calls.append({
                    "id": tc.get("id", f"call_{hash(func.get('name', ''))}"),
                    "name": func.get("name", ""),
                    "args": json.loads(func.get("arguments", "{}"))
                        if isinstance(func.get("arguments"), str)
                        else func.get("arguments", {}),
                })

            content = message.get("content") or ""
            ai_msg = AIMessage(content=content, tool_calls=lc_tool_calls)

            duration = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"[GenerateAnswer] 返回 tool_calls ({duration:.0f}ms)")

            # 只返回 messages（让 graph 路由到 execute_tool）
            return {
                "messages": [ai_msg],
                "web_search_triggered": True,
                "processing_log": [{
                    "stage": "generate_answer",
                    "action": "tool_calls_requested",
                    "tools": [tc["name"] for tc in lc_tool_calls],
                    "duration_ms": duration,
                }],
            }

        # 没有 tool_calls → 正常回答
        answer = (content or "").strip()

    except Exception as e:
        logger.error(f"[GenerateAnswer] Tool-calling 异常: {e}", exc_info=True)
        return _create_fallback_response(
            query, state.get("history_prompt", ""), state.get("history_messages", [])
        )

    if not answer:
        logger.warning("[GenerateAnswer] Tool-calling 返回空答案")
        return _create_fallback_response(
            query, state.get("history_prompt", ""), state.get("history_messages", [])
        )

    duration = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(f"[GenerateAnswer] Tool-calling 回答完成 ({duration:.0f}ms): {len(answer)} 字符")

    generation_output: GenerationOutput = {
        "answer": answer,
        "metadata": {
            "confidence": 0.7,
            "reasoning_type": "web_search",
            "grounded": True,
            "missing_info": False,
        },
        "citations": [],
        "follow_up_questions": _generate_follow_ups(query, answer),
    }

    return {
        "generation_output": generation_output,
        "web_search_used": True,
        "sources": [],
        "processing_log": [{
            "stage": "generate_answer",
            "duration_ms": duration,
            "query": query,
            "answer_length": len(answer),
            "mode": "tool_calling",
            "model": model,
        }],
    }


# ── ReAct Re-entry: Generate After Tool Call ──────────────────────────────────

def _generate_after_tool_call(state: dict, start_time: datetime) -> dict:
    """ReAct 回环：工具执行完后，基于完整对话历史生成最终答案"""
    query = state.get("rewritten_query") or state["original_query"]
    messages = state.get("messages", [])
    config = state.get("config", {})
    model = config.get("generate_model", settings.generation_model)

    # messages 中已有完整的 tool-calling 对话：
    # [HumanMsg(query), AIMsg(tool_calls), ToolMsg(result)]
    # 在它们前面加上 system prompt

    system_msg = {"role": "system", "content": TOOL_CALLING_SYSTEM.format(
        tool_descriptions="web_search: 搜索互联网获取实时信息"
    )}

    messages_for_llm = [system_msg]
    for msg in messages:
        if isinstance(msg, HumanMessage):
            messages_for_llm.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            content = msg.content or ""
            msg_dict = {"role": "assistant", "content": content}
            if msg.tool_calls:
                # 转换 tool_calls 为 DashScope 格式
                dashscope_tool_calls = []
                for tc in msg.tool_calls:
                    dashscope_tool_calls.append({
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                        },
                    })
                msg_dict["tool_calls"] = dashscope_tool_calls
            messages_for_llm.append(msg_dict)
        elif isinstance(msg, ToolMessage):
            messages_for_llm.append({
                "role": "tool",
                "content": msg.content,
                "tool_call_id": msg.tool_call_id,
            })

    # 最后一次 LLM 调用（不带 tools，强制生成答案）
    try:
        from service.llm_client import llm_call
        cfg = settings.get_llm_config("generation", model=model)
        result = llm_call(messages=messages_for_llm, model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=60)

        if result["status_code"] != 200:
            logger.error(f"[GenerateAnswer] ReAct 回环 LLM error: status={result['status_code']}")
            answer = "抱歉，处理搜索结果是出现了问题。"
        else:
            answer = (result["content"] or "").strip()

    except Exception as e:
        logger.error(f"[GenerateAnswer] ReAct 回环异常: {e}", exc_info=True)
        answer = "抱歉，处理搜索结果是出现了问题。"

    if not answer:
        answer = "基于搜索结果，我暂时无法给出完整答案。请尝试更具体的问题。"

    duration = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(f"[GenerateAnswer] ReAct 回环完成 ({duration:.0f}ms): {len(answer)} 字符")

    generation_output: GenerationOutput = {
        "answer": answer,
        "metadata": {
            "confidence": 0.75,
            "reasoning_type": "web_search_react",
            "grounded": True,
            "missing_info": False,
        },
        "citations": [],
        "follow_up_questions": _generate_follow_ups(query, answer),
    }

    return {
        "generation_output": generation_output,
        "web_search_used": True,
        "sources": [],
        "processing_log": [{
            "stage": "generate_answer",
            "duration_ms": duration,
            "query": query,
            "answer_length": len(answer),
            "mode": "react_loop",
            "model": model,
        }],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_history_section(history_prompt: str, history_messages: list) -> str:
    """构建历史对话上下文"""
    if history_prompt:
        return f"\n\n【历史对话摘要】\n{history_prompt}"
    if history_messages:
        lines = []
        for msg in history_messages:
            if hasattr(msg, "type"):
                if msg.type == "human":
                    lines.append(f"用户：{msg.content}")
                elif msg.type == "ai":
                    lines.append(f"助手：{msg.content or ''}")
        if lines:
            return "\n\n【近期对话】\n" + "\n".join(lines)
    return ""


def _build_tool_calling_messages(
    system_content: str, query: str, history_section: str,
    state: dict, tool_call_count: int
) -> list:
    """构建带工具调用的完整消息列表"""
    messages = [
        {"role": "system", "content": system_content},
    ]

    # 如果已有工具交互历史（多轮 tool-calling），把历史消息也加入
    all_messages = state.get("messages", [])
    has_tool_history = False
    for msg in all_messages:
        if isinstance(msg, ToolMessage):
            has_tool_history = True
            break

    if has_tool_history and tool_call_count > 0:
        for msg in all_messages:
            if isinstance(msg, HumanMessage):
                messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage) and msg.tool_calls:
                content = msg.content or ""
                tc_list = []
                for tc in msg.tool_calls:
                    tc_list.append({
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                        },
                    })
                messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tc_list,
                })
            elif isinstance(msg, ToolMessage):
                messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id,
                })
    else:
        # 首次 tool-calling
        user_content = f"用户问题：{query}{history_section}\n\n注意：知识库中没有找到相关信息。如果需要，请使用 web_search 工具搜索互联网。"
        messages.append({"role": "user", "content": user_content})

    return messages


def _format_tool_descriptions(registry) -> str:
    """格式化工具描述"""
    lines = []
    for name in registry.get_tool_names():
        tool_info = registry._tools.get(name, {})
        schema = tool_info.get("schema", {})
        desc = schema.get("description", "无描述")
        lines.append(f"- **{name}**: {desc}")
    return "\n".join(lines) if lines else "无可用工具"


def _call_llm(model: str, messages: list) -> str:
    """调用 LLM 并返回文本内容"""
    from service.llm_client import llm_call
    cfg = settings.get_llm_config("generation", model=model)
    result = llm_call(messages=messages, model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"], base_url=cfg["base_url"])
    if result["status_code"] == 200:
        return (result["content"] or "").strip()
    logger.error(f"[GenerateAnswer] LLM 调用失败: status={result['status_code']}")
    return ""


# ── 自检轮：检查信息遗漏并补充 ─────────────────────────────────────────

SELF_CHECK_PROMPT = """你是一个严格的质量检查专家。对比"当前回答"和"上下文材料"，检查回答是否有信息遗漏。

## 检查规则
1. 逐一检查上下文中的每个事实，看是否在回答中出现
2. 特别关注：数字、条件、名称、步骤等具体细节
3. 如果回答已经完整覆盖了上下文中的所有相关信息，回复 "COMPLETE"
4. 如果有遗漏，列出所有遗漏的信息点

## 输出格式
如果完整：只输出 "COMPLETE"
如果有遗漏：输出 "MISSING:" 后跟遗漏的信息列表，每行一个"""

SUPPLEMENT_PROMPT = """基于"当前回答"和"遗漏信息"，补充遗漏的内容，生成完整的回答。
保留原回答的结构和内容，只在相应位置补充遗漏的信息。
不要重复已有的信息，不要改变原回答的格式。"""


def _self_check_and_supplement(
    model: str, query: str, answer: str, context_text: str,
    sub_queries: list = None
) -> str:
    """自检轮：检查回答是否有信息遗漏，如有则补充"""
    try:
        # 构建子查询指引
        sub_query_section = ""
        if sub_queries:
            sub_query_section = (
                "\n\n请特别检查以下每个子问题是否都已完整回答：\n"
                + "\n".join(f"  {i+1}. {sq}" for i, sq in enumerate(sub_queries))
            )

        # Step 1: 检查遗漏
        check_messages = [
            {"role": "system", "content": SELF_CHECK_PROMPT},
            {"role": "user", "content": (
                f"用户问题：{query}\n"
                f"{sub_query_section}\n\n"
                f"当前回答：\n{answer}\n\n"
                f"上下文材料：\n{context_text[:4000]}\n\n"
                f"请检查回答是否有信息遗漏："
            )},
        ]

        check_result = _call_llm(model, check_messages)
        if not check_result:
            return answer

        # Step 2: 判断是否完整
        if "COMPLETE" in check_result.upper() and "MISSING" not in check_result.upper():
            logger.info("[SelfCheck] 回答完整，无需补充")
            return answer

        # Step 3: 有遗漏，生成补充回答
        logger.info(f"[SelfCheck] 发现遗漏，补充中...")
        logger.info(f"[SelfCheck] 遗漏信息: {check_result[:200]}")

        supplement_messages = [
            {"role": "system", "content": SUPPLEMENT_PROMPT},
            {"role": "user", "content": (
                f"用户问题：{query}\n\n"
                f"当前回答：\n{answer}\n\n"
                f"遗漏信息：\n{check_result}\n\n"
                f"上下文材料：\n{context_text[:4000]}\n\n"
                f"请生成补充后的完整回答："
            )},
        ]

        supplemented = _call_llm(model, supplement_messages)
        if supplemented and len(supplemented) > len(answer) * 0.5:
            logger.info(f"[SelfCheck] 补充完成: {len(answer)} → {len(supplemented)} 字符")
            return supplemented

        return answer

    except Exception as e:
        logger.error(f"[SelfCheck] 自检异常: {e}")
        return answer


def _build_citations(blocks: list) -> list:
    """构建 citations"""
    citations = []
    for i, block in enumerate(blocks):
        if i < 5:
            citations.append({
                "chunk_id": block["chunk_id"],
                "doc_id": block["doc_id"],
                "span": block["text"][:200],
                "confidence": block["score"],
            })
    return citations


def _build_metadata(chunks: list, answer: str, context_text: str) -> dict:
    """构建 metadata"""
    confidence = _calculate_confidence(chunks)
    grounded = _check_groundedness(answer, context_text)
    return {
        "confidence": confidence,
        "reasoning_type": "synthesis" if len(chunks) > 1 else "direct",
        "grounded": grounded,
        "missing_info": not grounded,
    }


def _build_sources(blocks: list) -> list:
    """构建 sources"""
    return [
        {
            "doc_id": block["doc_id"],
            "chunk_id": block["chunk_id"],
            "chunk_uuid": block["chunk_id"],  # MySQL 中的字段名
            "score": block["score"],
            "preview": block["text"][:300],
        }
        for block in blocks[:5]
    ]


# ── Fallback ──────────────────────────────────────────────────────────────────

def _create_fallback_response(query: str, history_prompt: str = "",
                               history_messages: list = None,
                               memory_context: str = "") -> dict:
    """
    创建备用响应 - 使用模型自身知识回答
    当没有检索结果且未启用联网搜索时使用
    """
    if history_messages is None:
        history_messages = []

    logger.info(f"[GenerateAnswer] Fallback: {query}")

    history_section = _build_history_section(history_prompt, history_messages)
    memory_section = f"\n{memory_context}" if memory_context else ""

    try:
        messages = [
            {
                "role": "system",
                "content": "你是一个智能助手。如果对话历史中包含相关信息，请优先使用。请用中文回答。"
            },
            {
                "role": "user",
                "content": f"用户问题：{query}{history_section}{memory_section}\n\n请回答："
            }
        ]

        from service.llm_client import llm_call
        cfg = settings.get_llm_config("generation")
        result = llm_call(messages=messages, model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=60)

        if result["status_code"] == 200:
            answer = (result["content"] or "抱歉，我无法回答这个问题。").strip()
        else:
            answer = f"抱歉，目前没有找到相关的参考资料。关于这个问题 \"{query}\"，我无法提供准确的信息。"
    except Exception as e:
        logger.error(f"[GenerateAnswer] Fallback 失败: {e}")
        answer = f"抱歉，目前没有找到相关的参考资料。"

    return {
        "generation_output": {
            "answer": answer,
            "metadata": {
                "confidence": 0.5,
                "reasoning_type": "general_knowledge",
                "grounded": False,
                "missing_info": False,
            },
            "citations": [],
            "follow_up_questions": _generate_follow_ups(query, answer),
        },
        "web_search_used": False,
        "context_pack": {
            "blocks": [],
            "total_tokens": 0,
            "compressed_text": "",
            "compression_ratio": 0.0,
        },
        "sources": [],
        "processing_log": [{
            "stage": "generate_answer",
            "status": "fallback_general_knowledge",
            "query": query,
            "answer_length": len(answer),
        }],
    }


# ── Existing Utilities (unchanged) ────────────────────────────────────────────

def build_context_pack(chunks: list, max_tokens: int = 4096) -> ContextPack:
    """构建上下文包"""
    blocks = []
    total_tokens = 0
    compressed_parts = []

    for i, chunk in enumerate(chunks):
        content = chunk.get("content", "")
        token_count = count_tokens(content)

        if total_tokens + token_count > max_tokens:
            logger.warning(
                f"[BuildContext] token 预算不足，截断 chunk[{i}] "
                f"(需要 {token_count}, 剩余 {max_tokens - total_tokens}, "
                f"chunk_id={chunk.get('chunk_id', '')[:12]}..., "
                f"已包含 {len(blocks)} 个 chunk)"
            )
            break

        blocks.append({
            "chunk_id": chunk.get("chunk_id", ""),
            "doc_id": chunk.get("doc_id", ""),
            "text": content,
            "token_count": token_count,
            "score": chunk.get("rerank_score") or chunk.get("hybrid_score") or 0.0,
        })

        compressed_parts.append(f"[片段 {i+1} | doc_id: {chunk.get('doc_id', 'N/A')}]\n{content}")
        total_tokens += token_count

    logger.info(
        f"[BuildContext] 最终包含 {len(blocks)}/{len(chunks)} 个 chunk, "
        f"{total_tokens}/{max_tokens} tokens"
    )

    compressed_text = "\n\n---\n\n".join(compressed_parts)
    compression_ratio = len(compressed_text) / total_tokens if total_tokens > 0 else 0

    return {
        "blocks": blocks,
        "total_tokens": total_tokens,
        "compressed_text": compressed_text,
        "compression_ratio": compression_ratio,
    }


def _calculate_confidence(chunks: list) -> float:
    if not chunks:
        return 0.0
    scores = [
        chunk.get("rerank_score") or chunk.get("hybrid_score") or chunk.get("vector_score") or 0.0
        for chunk in chunks[:5]
    ]
    if not scores:
        return 0.0
    avg_score = sum(scores) / len(scores)
    confidence = min(1.0, max(0.0, avg_score))
    if len(chunks) == 1:
        confidence *= 0.8
    elif len(chunks) >= 3:
        confidence *= 1.1
    return round(min(1.0, confidence), 2)


def _check_groundedness(answer: str, context_text: str) -> bool:
    """
    检测 answer 是否有 context 支撑（基于 bigram 重叠）
    返回 True 表示有依据，False 表示可能幻觉
    """
    if not answer or not context_text:
        return False
    if len(answer) < 20 and len(context_text) > 1000:
        return False
    if "[doc_id:" in answer or "[文档" in answer or "[片段" in answer:
        return True
    if "无法" in answer or "没有" in answer or "不足" in answer:
        return True

    # 基于 bigram 重叠的 groundedness 检测
    def _get_bigrams(text: str) -> set:
        import re
        chars = re.findall(r'[一-鿿]', text)
        words = re.findall(r'[a-zA-Z]+', text.lower())
        bigrams = set()
        for i in range(len(chars) - 1):
            bigrams.add(chars[i] + chars[i + 1])
        for i in range(len(words) - 1):
            bigrams.add(words[i] + ' ' + words[i + 1])
        return bigrams

    answer_bigrams = _get_bigrams(answer)
    context_bigrams = _get_bigrams(context_text)

    if not answer_bigrams:
        return False

    overlap = answer_bigrams & context_bigrams
    overlap_ratio = len(overlap) / len(answer_bigrams)
    return overlap_ratio >= 0.15


def _generate_follow_ups(query: str, answer: str) -> list:
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
    return follow_ups[:3]
