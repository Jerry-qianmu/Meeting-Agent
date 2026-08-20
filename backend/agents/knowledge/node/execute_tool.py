# -*- coding: utf-8 -*-
"""
Execute Tool Node — 执行 MCP 工具调用
从 state.messages 中提取 AIMessage.tool_calls，逐一调用 MCP 工具，
将结果以 ToolMessage 形式返回

注意：此节点在 asyncio.to_thread() 的线程中执行。
MCP 调用通过 run_coroutine_threadsafe 提交到主事件循环，
主事件循环此时空闲（graph 在子线程中），_read_loop 能正常处理响应。
"""

import json
import logging
from datetime import datetime
from typing import List

from langchain_core.messages import AIMessage, ToolMessage

logger = logging.getLogger(__name__)


def execute_tool(state: dict) -> dict:
    """
    执行 MCP 工具调用节点

    从消息列表中提取最后一条 AIMessage 的 tool_calls，
    调用对应的 MCP 工具，返回 ToolMessage 列表。
    """
    logger.info("[ExecuteTool] 执行工具调用")

    messages = state.get("messages", [])
    if not messages:
        logger.warning("[ExecuteTool] 没有消息，跳过")
        return {"messages": [], "tool_call_count": state.get("tool_call_count", 0)}

    last_message = messages[-1]
    tool_calls = _get_tool_calls(last_message)
    if not tool_calls:
        logger.warning("[ExecuteTool] 最后一条消息没有 tool_calls")
        return {"messages": [], "tool_call_count": state.get("tool_call_count", 0)}

    from service.MCP.mcp_tool_registry import get_mcp_registry_sync

    registry = get_mcp_registry_sync()
    if not registry or not registry.is_initialized:
        logger.error("[ExecuteTool] MCP 注册表未初始化")
        error_msg = ToolMessage(
            content="MCP 服务未初始化",
            tool_call_id=tool_calls[0].get("id", "unknown"),
        )
        return {
            "messages": [error_msg],
            "tool_call_count": state.get("tool_call_count", 0) + 1,
        }

    import asyncio
    import concurrent.futures

    loop = registry.main_loop
    if not loop:
        logger.error("[ExecuteTool] 无法获取主事件循环")
        error_msg = ToolMessage(
            content="内部错误：无法获取事件循环",
            tool_call_id=tool_calls[0].get("id", "unknown"),
        )
        return {
            "messages": [error_msg],
            "tool_call_count": state.get("tool_call_count", 0) + 1,
        }

    tool_messages = []
    start_time = datetime.now()
    logs = []

    for tc in tool_calls:
        tool_name = tc.get("name", "")
        tool_args = tc.get("args", {}) or tc.get("arguments", {})
        tool_call_id = tc.get("id", f"call_{hash(tool_name)}")

        logger.info(
            f"[ExecuteTool] 调用: {tool_name}"
            f"({json.dumps(tool_args, ensure_ascii=False)[:200]})"
        )

        try:
            future = asyncio.run_coroutine_threadsafe(
                registry.call_tool(tool_name, tool_args), loop
            )
            result = future.result(timeout=60)

            logger.info(f"[ExecuteTool] {tool_name} 完成: {len(result)} chars")

            tool_messages.append(
                ToolMessage(content=result, tool_call_id=tool_call_id)
            )
            logs.append({
                "stage": "execute_tool",
                "tool": tool_name,
                "args": tool_args,
                "result_length": len(result),
                "success": True,
            })

        except concurrent.futures.TimeoutError:
            logger.error(f"[ExecuteTool] {tool_name} 超时 (60s)")
            tool_messages.append(
                ToolMessage(
                    content=f"工具调用超时",
                    tool_call_id=tool_call_id,
                )
            )
            logs.append({
                "stage": "execute_tool",
                "tool": tool_name,
                "error": "timeout",
                "success": False,
            })
        except Exception as e:
            logger.error(f"[ExecuteTool] {tool_name} 失败: {e}")
            tool_messages.append(
                ToolMessage(
                    content=f"工具调用失败: {str(e)}",
                    tool_call_id=tool_call_id,
                )
            )
            logs.append({
                "stage": "execute_tool",
                "tool": tool_name,
                "error": str(e),
                "success": False,
            })

    duration = (datetime.now() - start_time).total_seconds() * 1000
    logger.info(
        f"[ExecuteTool] 完成 ({duration:.0f}ms): {len(tool_messages)} 个工具调用"
    )

    new_count = state.get("tool_call_count", 0) + len(tool_calls)

    return {
        "messages": tool_messages,
        "tool_call_count": new_count,
        "processing_log": logs,
    }


def _get_tool_calls(message) -> List[dict]:
    """安全获取 tool_calls"""
    if isinstance(message, AIMessage):
        return message.tool_calls or []
    if hasattr(message, "tool_calls"):
        return message.tool_calls or []
    return []
