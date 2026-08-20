# -*- coding: utf-8 -*-
"""
MCP Client — 通过 stdio 子进程与 MCP Server 通信
协议：JSON-RPC 2.0，消息以 \n 分隔
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 异常定义 ──────────────────────────────────────────────────────────────────


class MCPError(Exception):
    """MCP 通用错误"""
    pass


class MCPServerStartError(MCPError):
    """MCP Server 启动失败"""
    pass


class MCPToolCallError(MCPError):
    """工具调用失败"""
    pass


class MCPTimeoutError(MCPError):
    """超时"""
    pass


# ── MCP Client ────────────────────────────────────────────────────────────────


class MCPClient:
    """
    MCP 客户端 — 管理一个 stdio 子进程并通过 JSON-RPC 通信

    用法:
        client = MCPClient(["npx", "-y", "tavily-mcp"], {"TAVILY_API_KEY": "..."})
        await client.start()
        tools = await client.list_tools()
        result = await client.call_tool("web_search", {"query": "..."})
        await client.close()
    """

    def __init__(
        self,
        server_command: List[str],
        server_env: Optional[Dict[str, str]] = None,
        startup_timeout: float = 15.0,
        call_timeout: float = 30.0,
    ):
        import shutil

        # ── 命令解析：将 "npx" 解析为完整路径（Windows .CMD 需要完整路径）──
        resolved_cmd = list(server_command)
        exe_name = resolved_cmd[0]
        exe_path = shutil.which(exe_name) or shutil.which(exe_name + ".cmd")
        if exe_path and exe_path != exe_name:
            resolved_cmd[0] = exe_path
            logger.debug(f"[MCP] 命令解析: {exe_name} → {exe_path}")

        self.server_command = resolved_cmd
        self.server_env = {**os.environ, **(server_env or {})}
        self.startup_timeout = startup_timeout
        self.call_timeout = call_timeout

        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._initialized = False
        self._shutdown = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动 MCP Server 子进程并进行初始化握手"""
        if self._process is not None:
            return

        logger.info(f"[MCP] 启动 Server: {' '.join(self.server_command)}")

        try:
            self._process = await asyncio.create_subprocess_exec(
                *self.server_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.server_env,
            )
        except FileNotFoundError as e:
            raise MCPServerStartError(
                f"找不到命令 '{self.server_command[0]}'，请确保已安装。"
                f" 原始错误: {e}"
            )
        except Exception as e:
            raise MCPServerStartError(f"启动 MCP Server 失败: {e}")

        # 启动 stdout 读取循环
        self._reader_task = asyncio.ensure_future(self._read_loop())

        # MCP 初始化握手: initialize → initialized
        try:
            init_result = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "MyAgent-MCP-Client", "version": "1.0.0"},
                },
                timeout=self.startup_timeout,
            )
            logger.info(f"[MCP] 初始化完成: {init_result.get('serverInfo', {})}")

            # 发送 initialized 通知（不需要响应）
            self._send_notification("notifications/initialized", {})
            self._initialized = True

        except MCPTimeoutError:
            await self._kill_process()
            raise MCPServerStartError(
                f"MCP Server 初始化超时 ({self.startup_timeout}s)"
            )
        except Exception as e:
            await self._kill_process()
            raise MCPServerStartError(f"MCP 初始化握手失败: {e}")

    async def close(self) -> None:
        """关闭连接，终止子进程"""
        self._shutdown = True
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        await self._kill_process()
        logger.info("[MCP] 连接已关闭")

    async def _kill_process(self) -> None:
        """安全终止子进程"""
        if self._process is None:
            return
        try:
            if self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
        except ProcessLookupError:
            pass
        self._process = None

    # ── MCP Protocol Methods ──────────────────────────────────────────────

    async def list_tools(self) -> List[Dict[str, Any]]:
        """获取 Server 提供的工具列表 → tools/list"""
        result = await self._send_request("tools/list", {})
        tools = result.get("tools", [])
        logger.info(f"[MCP] 获取到 {len(tools)} 个工具: {[t['name'] for t in tools]}")
        return tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """调用指定工具 → tools/call"""
        result = await self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
            timeout=self.call_timeout,
        )
        return result

    # ── JSON-RPC Core ─────────────────────────────────────────────────────

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(
        self, method: str, params: Dict[str, Any], timeout: Optional[float] = None
    ) -> Any:
        """发送 JSON-RPC 请求并等待响应"""
        if not self._process or self._process.returncode is not None:
            raise MCPError("MCP Server 未运行")

        req_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        # 注册等待的 Future
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        try:
            # 发送请求
            raw = json.dumps(request, ensure_ascii=False) + "\n"
            self._process.stdin.write(raw.encode("utf-8"))
            await self._process.stdin.drain()

            # 等待响应
            effective_timeout = timeout or self.call_timeout
            return await asyncio.wait_for(future, timeout=effective_timeout)

        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise MCPTimeoutError(
                f"请求 '{method}' 超时 ({effective_timeout}s)"
            )
        except Exception:
            self._pending.pop(req_id, None)
            raise

    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """发送 JSON-RPC 通知（无需响应，fire-and-forget）"""
        if not self._process or self._process.returncode is not None:
            return
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        raw = json.dumps(notification, ensure_ascii=False) + "\n"
        self._process.stdin.write(raw.encode("utf-8"))
        # 注意：sync 上下文无法 await drain()，但 write + 后续的 drain（在下一次
        # _send_request 中）会携带这些字节一起发送，不影响协议正确性

    async def _read_loop(self) -> None:
        """持续读取 stdout，将响应路由到对应的 Future"""
        buffer = b""
        try:
            while not self._shutdown:
                # 按行读取
                chunk = await self._process.stdout.readline()
                if not chunk:
                    # EOF — 子进程退出
                    logger.warning("[MCP] Server stdout 关闭")
                    break

                line = chunk.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(f"[MCP] 非 JSON 输出: {line[:200]}")
                    continue

                # 处理响应
                msg_id = message.get("id")
                if msg_id is not None and msg_id in self._pending:
                    future = self._pending.pop(msg_id)
                    if "error" in message:
                        err = message["error"]
                        future.set_exception(
                            MCPToolCallError(
                                f"MCP Error [{err.get('code', -1)}]: {err.get('message', 'Unknown')}"
                            )
                        )
                    else:
                        future.set_result(message.get("result", {}))
                else:
                    # 可能是通知或其他消息
                    logger.debug(f"[MCP] 收到非请求响应: {message.get('method', '?')}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[MCP] 读取循环异常: {e}", exc_info=True)
        finally:
            # 清理所有等待中的请求
            for req_id, future in list(self._pending.items()):
                if not future.done():
                    future.set_exception(MCPError("MCP Server 连接已断开"))
            self._pending.clear()

    # ── Health Check ──────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return (
            self._initialized
            and self._process is not None
            and self._process.returncode is None
        )
