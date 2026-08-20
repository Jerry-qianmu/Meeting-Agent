# -*- coding: utf-8 -*-
"""
统一 LLM 调用客户端
支持 DashScope 和 OpenAI 协议，通过环境变量切换
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

_settings = None


def _get_settings():
    global _settings
    if _settings is None:
        from config.settings import Settings
        _settings = Settings()
    return _settings


def llm_call(
    messages: List[Dict[str, str]],
    model: str = None,
    api_type: str = None,
    api_key: str = None,
    base_url: str = None,
    temperature: float = None,
    tools: list = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    统一 LLM 调用

    Args:
        messages: [{"role": "system"/"user"/"assistant", "content": "..."}]
        model: 模型名
        api_type: "dashscope" 或 "openai"，默认从 settings 读
        api_key: API Key，默认从 settings 读
        base_url: OpenAI 协议的 base_url
        temperature: 温度
        tools: 工具 schemas（tool-calling）
        timeout: 超时秒数

    Returns:
        {"content": str, "tool_calls": list or None, "status_code": int, "raw": response}
    """
    s = _get_settings()
    api_type = api_type or s.llm_api_type
    api_key = api_key or s.llm_api_key
    model = model or s.generation_model

    if api_type == "openai":
        return _call_openai(messages, model, api_key, base_url or s.llm_base_url, temperature, tools, timeout)
    else:
        return _call_dashscope(messages, model, api_key, temperature, tools, timeout)


def _call_dashscope(
    messages: List[Dict], model: str, api_key: str,
    temperature: float, tools: list, timeout: int,
) -> Dict[str, Any]:
    """DashScope Generation.call 封装"""
    from dashscope import Generation

    kwargs = {
        "api_key": api_key,
        "model": model,
        "messages": messages,
        "result_format": "message",
        "timeout": timeout,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if tools:
        kwargs["tools"] = tools

    try:
        resp = Generation.call(**kwargs)

        if resp.status_code != 200:
            logger.warning(f"[LLM] DashScope error: status={resp.status_code}, model={model}, message={getattr(resp, 'message', '')}")
            return {"content": "", "tool_calls": None, "status_code": resp.status_code, "raw": resp}

        choice = resp.output.choices[0]
        msg = choice.message
        content = msg.get("content", "") or ""
        tool_calls = msg.get("tool_calls") or None

        return {"content": content, "tool_calls": tool_calls, "status_code": 200, "raw": resp}

    except Exception as e:
        logger.error(f"[LLM] DashScope 异常: {e}")
        return {"content": "", "tool_calls": None, "status_code": -1, "raw": None}


def _call_openai(
    messages: List[Dict], model: str, api_key: str, base_url: str,
    temperature: float, tools: list, timeout: int,
) -> Dict[str, Any]:
    """OpenAI 协议封装"""
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("[LLM] openai 包未安装: pip install openai")
        return {"content": "", "tool_calls": None, "status_code": -1, "raw": None}

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)

        kwargs = {
            "model": model,
            "messages": messages,
            "timeout": timeout,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools

        resp = client.chat.completions.create(**kwargs)

        choice = resp.choices[0]
        content = choice.message.content or ""
        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                {"id": tc.id, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in choice.message.tool_calls
            ]

        return {"content": content, "tool_calls": tool_calls, "status_code": 200, "raw": resp}

    except Exception as e:
        logger.error(f"[LLM] OpenAI 异常: {e}")
        return {"content": "", "tool_calls": None, "status_code": -1, "raw": None}
