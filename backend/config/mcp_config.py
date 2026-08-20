# -*- coding: utf-8 -*-
"""
MCP 配置
管理 MCP Server 连接参数和环境变量
"""

import os
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class MCPServerConfig:
    """单个 MCP Server 配置"""
    name: str                          # 唯一标识名
    command: List[str]                 # 启动命令，如 ["npx", "-y", "tavily-mcp"]
    env: Dict[str, str] = field(default_factory=dict)  # 环境变量
    enabled: bool = True               # 是否启用
    description: str = ""              # 描述


class MCPConfig:
    """MCP 全局配置"""

    # ── Tavily Web Search ──
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # ── MCP 全局参数 ──
    tool_call_timeout: int = int(os.getenv("MCP_TOOL_CALL_TIMEOUT", "30"))   # 单次工具调用超时(秒)
    server_startup_timeout: int = int(os.getenv("MCP_SERVER_STARTUP_TIMEOUT", "15"))  # 服务启动超时
    max_tool_calls_per_turn: int = int(os.getenv("MCP_MAX_TOOL_CALLS", "5"))  # 每轮最大工具调用次数

    # ── MCP Server 列表 ──
    @staticmethod
    def get_servers() -> List[MCPServerConfig]:
        """获取所有已配置的 MCP Server"""
        servers = []

        # Web Search Server (Tavily)
        if MCPConfig.tavily_api_key:
            servers.append(MCPServerConfig(
                name="web_search",
                command=["npx", "-y", "tavily-mcp"],
                env={"TAVILY_API_KEY": MCPConfig.tavily_api_key},
                enabled=True,
                description="Tavily web search for real-time information"
            ))

        # 未来扩展：添加更多 server
        # servers.append(MCPServerConfig(
        #     name="calculator",
        #     command=["python", "-m", "mcp_calculator"],
        #     enabled=True
        # ))

        return servers


# 单例
_mcp_config: Optional[MCPConfig] = None


def get_mcp_config() -> MCPConfig:
    """获取 MCP 配置单例"""
    global _mcp_config
    if _mcp_config is None:
        _mcp_config = MCPConfig()
    return _mcp_config
