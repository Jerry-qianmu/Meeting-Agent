# -*- coding: utf-8 -*-
"""
MCP 工具注册表
- 管理所有 MCP Server 的生命周期
- 将 MCP 工具转换为 LangChain BaseTool
- 提供 OpenAI function-calling 格式 schema（用于 DashScope API）
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Type

from langchain_core.tools import BaseTool, StructuredTool

from config.mcp_config import get_mcp_config, MCPServerConfig
from service.MCP.mcp_client import MCPClient

logger = logging.getLogger(__name__)


class MCPToolRegistry:
    """
    MCP 工具注册表

    用法:
        registry = MCPToolRegistry()
        await registry.initialize()

        # 获取 LangChain tools
        tools = registry.get_langchain_tools()

        # 获取 OpenAI function calling schemas
        schemas = registry.get_tool_schemas()

        # 调用工具
        result = await registry.call_tool("web_search", {"query": "..."})

        # 关闭
        await registry.shutdown()
    """

    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._langchain_tools: List[BaseTool] = []
        self._initialized = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None  # 主事件循环引用

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """启动所有 MCP Server 并注册工具"""
        if self._initialized:
            return

        # 捕获主事件循环（供 execute_tool 线程使用）
        self._loop = asyncio.get_running_loop()

        config = get_mcp_config()
        servers = config.get_servers()

        if not servers:
            logger.info("[MCPRegistry] 没有配置 MCP Server，跳过初始化")
            self._initialized = True
            return

        for server_config in servers:
            if not server_config.enabled:
                continue
            try:
                await self._register_server(server_config)
            except Exception as e:
                logger.error(
                    f"[MCPRegistry] 注册 Server '{server_config.name}' 失败: {e}",
                    exc_info=True,
                )

        self._initialized = True
        logger.info(
            f"[MCPRegistry] 初始化完成: {len(self._tools)} 个工具, "
            f"{len(self._clients)} 个 Server"
        )

    async def shutdown(self) -> None:
        """关闭所有 MCP Server 连接"""
        for name, client in list(self._clients.items()):
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"[MCPRegistry] 关闭 '{name}' 异常: {e}")
        self._clients.clear()
        self._tools.clear()
        self._langchain_tools.clear()
        self._initialized = False
        logger.info("[MCPRegistry] 已关闭")

    async def _register_server(self, server_config: MCPServerConfig) -> None:
        """注册单个 MCP Server"""
        client = MCPClient(
            server_command=server_config.command,
            server_env=server_config.env,
            startup_timeout=get_mcp_config().server_startup_timeout,
            call_timeout=get_mcp_config().tool_call_timeout,
        )
        await client.start()
        self._clients[server_config.name] = client

        # 获取工具列表
        mcp_tools = await client.list_tools()
        for tool_schema in mcp_tools:
            tool_name = tool_schema["name"]
            qualified_name = f"mcp__{server_config.name}__{tool_name}"  # 防止名称冲突

            lc_tool = self._mcp_to_langchain_tool(
                server_config.name, qualified_name, tool_schema, client
            )

            self._tools[qualified_name] = {
                "schema": tool_schema,
                "client_name": server_config.name,
                "lc_tool": lc_tool,
                "description": server_config.description,
            }
            self._langchain_tools.append(lc_tool)

            logger.info(
                f"[MCPRegistry] 注册工具: {qualified_name} "
                f"({tool_schema.get('description', '')[:60]})"
            )

    # ── Tool Conversion ───────────────────────────────────────────────────

    def _mcp_to_langchain_tool(
        self,
        server_name: str,
        qualified_name: str,
        mcp_schema: Dict[str, Any],
        client: MCPClient,
    ) -> BaseTool:
        """将 MCP tool schema 转换为 LangChain StructuredTool"""

        tool_name = mcp_schema["name"]
        description = mcp_schema.get("description", f"MCP tool: {tool_name}")
        input_schema = mcp_schema.get("inputSchema", {})

        # 构建参数模型：从 MCP inputSchema 动态生成 args_schema
        # 由于 MCP schema 是动态的，使用通用 args_schema 或 infer
        from pydantic import create_model, Field

        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        # 动态创建 Pydantic 模型用于参数验证
        field_defs = {}
        for prop_name, prop_info in properties.items():
            prop_type = self._json_type_to_python(prop_info.get("type", "string"))
            is_required = prop_name in required
            default = ... if is_required else prop_info.get("default", None)
            field_defs[prop_name] = (
                prop_type,
                Field(default, description=prop_info.get("description", "")),
            )

        if field_defs:
            ArgsModel = create_model(f"{tool_name}_args", **field_defs)
        else:
            # 无参数工具
            from pydantic import BaseModel
            ArgsModel = create_model(f"{tool_name}_args", __base__=BaseModel)

        # 创建异步调用函数
        async def _call_tool(**kwargs) -> str:
            try:
                result = await client.call_tool(tool_name, kwargs)
                return self._extract_text_content(result)
            except Exception as e:
                return f"工具调用失败: {e}"

        # 同步包装器（LangChain 需要同步 call）
        def _sync_call(**kwargs) -> str:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 已在事件循环中，创建新任务
                    import concurrent.futures
                    future = asyncio.run_coroutine_threadsafe(
                        _call_tool(**kwargs), loop
                    )
                    return future.result(timeout=client.call_timeout)
                else:
                    return asyncio.run(_call_tool(**kwargs))
            except Exception as e:
                return f"工具调用失败: {e}"

        tool = StructuredTool(
            name=qualified_name,
            description=description,
            args_schema=ArgsModel,
            func=_sync_call,
            coroutine=_call_tool,
        )

        return tool

    # ── Tool Calling ──────────────────────────────────────────────────────

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """调用指定工具（通过 MCP）"""
        tool_info = self._tools.get(tool_name)
        if not tool_info:
            return f"错误：未找到工具 '{tool_name}'"

        client = self._clients.get(tool_info["client_name"])
        if not client or not client.is_connected:
            return f"错误：MCP Server '{tool_info['client_name']}' 未连接"

        try:
            original_name = tool_info["schema"]["name"]
            result = await client.call_tool(original_name, arguments)
            return self._extract_text_content(result)
        except Exception as e:
            logger.error(f"[MCPRegistry] 调用 '{tool_name}' 失败: {e}")
            return f"工具调用失败: {e}"

    # ── Public API ────────────────────────────────────────────────────────

    def get_langchain_tools(self) -> List[BaseTool]:
        """获取所有 LangChain 格式的工具"""
        return list(self._langchain_tools)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        获取 OpenAI function-calling 格式的工具 schemas
        用于传给 DashScope Generation API 的 tools 参数
        """
        schemas = []
        for qualified_name, info in self._tools.items():
            mcp_schema = info["schema"]
            schemas.append({
                "type": "function",
                "function": {
                    "name": qualified_name,
                    "description": mcp_schema.get("description", ""),
                    "parameters": {
                        "type": "object",
                        "properties": mcp_schema.get("inputSchema", {}).get("properties", {}),
                        "required": mcp_schema.get("inputSchema", {}).get("required", []),
                    },
                },
            })
        return schemas

    def get_tool_names(self) -> List[str]:
        """获取所有工具名称"""
        return list(self._tools.keys())

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def main_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """主事件循环引用（供 execute_tool 线程使用）"""
        return self._loop

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _extract_text_content(result: Any) -> str:
        """从 MCP tools/call 响应中提取文本内容"""
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            content = result.get("content", [])
            if isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        texts.append(item.get("text", ""))
                return "\n".join(texts) if texts else json.dumps(result, ensure_ascii=False)
            return json.dumps(result, ensure_ascii=False)
        return str(result)

    @staticmethod
    def _json_type_to_python(json_type: str) -> Type:
        """JSON Schema type → Python type"""
        mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        return mapping.get(json_type, str)


# ── Singleton ────────────────────────────────────────────────────────────────

_registry: Optional[MCPToolRegistry] = None


async def get_mcp_registry() -> MCPToolRegistry:
    """获取 MCP 工具注册表单例（需要异步初始化）"""
    global _registry
    if _registry is None:
        _registry = MCPToolRegistry()
        await _registry.initialize()
    return _registry


def get_mcp_registry_sync() -> Optional[MCPToolRegistry]:
    """同步获取（可能未初始化）"""
    return _registry


async def shutdown_mcp_registry() -> None:
    """关闭 MCP 注册表"""
    global _registry
    if _registry:
        await _registry.shutdown()
        _registry = None
