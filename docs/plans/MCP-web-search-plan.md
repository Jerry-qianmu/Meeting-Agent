# MCP 工具调用集成方案 — 联网搜索

> 项目: MyAgent 知识库管理系统  
> 日期: 2026-05-24  
> 状态: 待审查  
> 目标: 在现有 LangGraph Agent 中集成 MCP (Model Context Protocol)，实现工具调用能力，第一阶段先加入联网搜索

---

## 1. 目标概述

### 1.1 现阶段目标

- 实现 MCP Client，能连接一个或多个 MCP Server
- 第一个工具：**联网搜索**（web_search），让 Agent 在知识库无法回答时自动联网获取信息
- 以 **LangGraph tool-calling (ReAct) 模式** 集成，而非硬编码路由，方便后续扩展更多工具

### 1.2 未来可扩展的工具

| 工具 | MCP Server | 用途 |
|------|-----------|------|
| `web_search` | tavily-mcp / brave-search | 联网搜索 |
| `calculator` | 内置 / mcp-calculator | 数学计算 |
| `weather` | openweather-mcp | 天气查询 |
| `file_read` | filesystem-mcp | 本地文件读取 |

---

## 2. MCP 协议简述

MCP (Model Context Protocol) 是 Anthropic 提出的标准化协议，定义了 LLM 应用与外部工具/数据源之间的通信方式。

```
┌──────────────┐     JSON-RPC over stdio/HTTP     ┌──────────────┐
│  MCP Client  │ ◄──────────────────────────────► │  MCP Server  │
│  (我们的Agent) │   tools/list, tools/call         │  (web_search)│
└──────────────┘                                  └──────────────┘
```

核心协议消息：
- `tools/list` — 客户端查询服务器提供了哪些工具
- `tools/call` — 客户端调用指定工具

传输方式：
- **stdio**（推荐起步）：MCP Server 作为子进程，通过标准输入输出通信
- **HTTP SSE**：通过 HTTP + Server-Sent Events 通信（适用于远程工具）

---

## 3. 整体架构设计

### 3.1 集成位置：LangGraph Tool-Calling 模式

在现有的 `generate_answer` 节点中引入 tool-calling 循环，而非新增独立节点：

```
现有流程（不变）:
START → memory_manager → query_rewrite → target_kb → target_doc
→ determine_strategy → retrieve_chunks → filter_chunks → rerank
→ generate_answer ──→ check_quality → retrieve_quality_hit → END
       │                                                        ↑
       │  新增 tool-calling 循环                                 │
       │  ┌──────────────────────────────────────┐              │
       └──► LLM decides: need tool?              │              │
            ├─ NO  → 生成最终答案 → 继续原流程 ──┘              │
            └─ YES → execute_tool (MCP) → 将结果注入消息         │
                     └─ 回到 LLM 再次决策 ──────┘               │
```

### 3.2 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 集成方式 | Tool-calling ReAct 循环 | LangGraph 原生支持，LLM 自主决定何时调用工具 |
| 传输协议 | stdio | 本地部署，简单可靠，无需额外网络端口 |
| MCP Server | 外部独立进程 | 解耦，方便替换不同的搜索服务商 |
| 工具发现 | 启动时注册 + 运行时可用 | 启动一次，性能好；不阻塞请求 |
| 结果注入 | 作为 LangChain ToolMessage | 与 LangGraph 消息流无缝集成 |

---

## 4. 组件设计

### 4.1 目录结构

```
backend/
├── service/
│   └── MCP/                          # 新增 MCP 服务模块
│       ├── __init__.py
│       ├── mcp_client.py             # MCP 客户端（已有空文件，需实现）
│       ├── mcp_tool_registry.py      # 工具注册表（管理工具生命周期）
│       └── servers/                  # MCP Server 子进程配置
│           └── web_search_server.py  # web_search server 启动器
├── agents/
│   └── knowledge/
│       ├── node/
│       │   ├── generate_answer.py    # [修改] 加入 tool-calling 循环
│       │   └── execute_tool.py       # [新增] MCP 工具执行节点
│       ├── state.py                  # [修改] 新增 MCP 相关状态字段
│       └── graph.py                  # [修改] 注册新节点和条件边
├── config/
│   └── mcp_config.py                 # MCP 配置（server 列表、超时等）
└── tools/                            # [可选] 非 MCP 的本地工具
    └── web_search_local.py           # [可选] 内置 web search 兜底实现
```

### 4.2 MCP Client (`service/MCP/mcp_client.py`)

**职责**：封装 JSON-RPC 通信，管理子进程生命周期。

```python
class MCPClient:
    """MCP 客户端，通过 stdio 与 MCP Server 通信"""
    
    def __init__(self, server_command: list[str], server_env: dict = None):
        """
        Args:
            server_command: 启动命令，如 ["npx", "@anthropic/mcp-server-brave-search"]
            server_env: 环境变量，如 {"BRAVE_API_KEY": "xxx"}
        """
        self.server_command = server_command
        self.server_env = server_env
        self._process: subprocess.Popen = None
        self._request_id = 0
    
    async def start(self) -> None:
        """启动 MCP Server 子进程并进行初始化握手"""
        # 1. 启动子进程
        # 2. 发送 initialize 请求
        # 3. 发送 initialized 通知
        
    async def list_tools(self) -> list[dict]:
        """获取服务器提供的工具列表 → tools/list"""
        
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """调用指定工具 → tools/call"""
        
    async def close(self) -> None:
        """关闭连接，终止子进程"""
```

核心实现要点：
- 使用 `asyncio.create_subprocess_exec` 管理子进程
- JSON-RPC 消息以 `\n` 分隔
- 每个请求有唯一 `id`，等待对应 `id` 的响应

### 4.3 工具注册表 (`service/MCP/mcp_tool_registry.py`)

**职责**：管理多个 MCP Server，聚合工具，转换为 LangChain Tool 格式。

```python
class MCPToolRegistry:
    """MCP 工具注册表 - 管理所有 MCP Server 的工具"""
    
    def __init__(self):
        self._clients: dict[str, MCPClient] = {}     # server_name -> client
        self._tools: list[BaseTool] = []              # LangChain tools
        self._tool_schemas: list[dict] = []            # OpenAI function schemas
    
    async def register_server(self, name: str, client: MCPClient) -> None:
        """注册一个 MCP Server，获取其工具列表"""
        await client.start()
        tools = await client.list_tools()
        # 将 MCP 工具转换为 LangChain BaseTool
        for tool in tools:
            lc_tool = self._mcp_to_langchain_tool(name, tool)
            self._tools.append(lc_tool)
    
    def get_langchain_tools(self) -> list[BaseTool]:
        """获取所有 LangChain 格式的工具"""
        return self._tools
    
    def get_tool_schemas(self) -> list[dict]:
        """获取 OpenAI function calling 格式的 schemas"""
        # 用于传给 DashScope API 的 tools 参数
    
    def _mcp_to_langchain_tool(self, server_name: str, mcp_tool: dict) -> BaseTool:
        """MCP tool schema → LangChain StructuredTool"""
```

### 4.4 Web Search MCP Server

**方案**：使用现成的社区 MCP Server，不自己写。推荐选项：

| Server | 安装命令 | API Key | 日免费额度 |
|--------|---------|---------|-----------|
| `tavily-mcp` | `npx -y tavily-mcp` | Tavily | 1000 次 |
| `mcp-server-brave-search` | `npx @anthropic/mcp-server-brave-search` | Brave | 2000 次 |
| `serena-mcp-web-search` | `uvx serena-mcp-web-search` | 无需 | 有限 |

**推荐 `tavily-mcp`**（专为 RAG 设计的搜索 API，返回结构化结果，带内容摘要）。

配置方式（`.env`）：
```bash
# MCP Web Search
TAVILY_API_KEY=tvly-xxxxxxxxxxxxx
MCP_WEB_SEARCH_COMMAND=npx -y tavily-mcp
```

### 4.5 工具执行节点 (`agents/knowledge/node/execute_tool.py`)

```python
def execute_tool(state: KnowledgeAgentState) -> dict:
    """
    执行 MCP 工具调用
    
    从 state.messages 中提取最后一条 AIMessage 的 tool_calls，
    逐一执行，将结果以 ToolMessage 形式返回。
    """
    # 1. 获取最后一条 AIMessage 的 tool_calls
    # 2. 对每个 tool_call，通过 MCPToolRegistry.call_tool() 执行
    # 3. 返回 ToolMessage 列表（追加到 messages）
    return {"messages": tool_messages}
```

### 4.6 generate_answer 修改

当前 `generate_answer` 是单次 LLM 调用。修改后变为 **tool-calling 循环**：

```python
def generate_answer(state: KnowledgeAgentState) -> dict:
    """
    增强版 generate_answer — 支持 tool-calling
    
    流程:
    1. 构建 messages（system + 检索到的上下文 + 历史 + 用户问题）
    2. 调用 LLM（带 tools 参数）
    3. 如果 LLM 返回 tool_calls → 返回 AIMessage（含 tool_calls），
       由 graph 的条件边路由到 execute_tool
    4. 如果 LLM 返回普通内容 → 解析为 GenerationOutput，继续原流程
    """
```

关键：tools 参数传给 DashScope Generation API：
```python
response = Generation.call(
    model=settings.generation_model,
    messages=messages,
    tools=mcp_registry.get_tool_schemas(),  # ← 新增
    result_format='message',
)
```

### 4.7 State 修改 (`state.py`)

新增字段：
```python
class KnowledgeAgentState(TypedDict, total=False):
    # ... 现有字段 ...
    
    # =========================================================
    # MCP Tool Calling
    # =========================================================
    available_tools: List[dict]              # 可用工具 schemas（传给 LLM）
    tool_call_count: int                      # 当前轮工具调用次数（防止死循环）
    max_tool_calls: int                       # 最大工具调用次数（默认 5）
    web_search_results: Optional[List[dict]]  # 联网搜索结果
```

### 4.8 Graph 修改 (`graph.py`)

新增节点和条件边：

```python
# 新增节点
knowledge_agent_graph.add_node("execute_tool", execute_tool)

# 新增条件边：generate_answer 之后判断是否需要调用工具
knowledge_agent_graph.add_conditional_edges(
    "generate_answer",
    should_call_tool,          # ← 新增条件函数
    {
        "call_tool": "execute_tool",   # 需要 → 去执行工具
        "continue": "check_quality",   # 不需要 → 继续质量评估
    }
)

# execute_tool 之后回到 generate_answer（ReAct 循环）
knowledge_agent_graph.add_edge("execute_tool", "generate_answer")
```

条件函数：
```python
def should_call_tool(state: KnowledgeAgentState) -> Literal["call_tool", "continue"]:
    """判断是否需要调用 MCP 工具"""
    # 1. 检查最后一条 AIMessage 是否有 tool_calls
    # 2. 检查 tool_call_count < max_tool_calls（防止死循环）
    # 3. 检查是否有可用工具
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if state.get("tool_call_count", 0) < state.get("max_tool_calls", 5):
            return "call_tool"
    return "continue"
```

---

## 5. 数据流示例

用户问："2026年诺贝尔物理学奖得主是谁？"（知识库没有这个信息）

```
1. memory_manager → 加载历史
2. query_rewrite → 改写查询
3. target_kb → 目标知识库为空（无匹配 KB）
4. target_doc → 目标文档为空
5. determine_strategy → vector
6. retrieve_chunks → 无结果（空列表）
7. filter_chunks → 空
8. rerank → 空
9. ┌─ generate_answer ─────────────────────────────────────┐
   │ LLM 收到：                                            │
   │   - System: 你是知识助手，可用工具: [web_search]      │
   │   - Context: (空, 知识库无结果)                        │
   │   - User: "2026年诺贝尔物理学奖得主是谁？"             │
   │                                                        │
   │ LLM 决定 → tool_calls: [{name: "web_search",           │
   │              args: {query: "2026年诺贝尔物理学奖得主"}}]│
   └────────────────────────────────────────────────────────┘
10. should_call_tool → "call_tool"
11. execute_tool → 调用 MCP web_search → 返回搜索结果
12. ┌─ generate_answer (第2轮) ────────────────────────────┐
    │ LLM 收到：                                           │
    │   - 上一轮 AIMessage (含 tool_calls)                  │
    │   - ToolMessage (web_search 返回结果)                 │
    │   - LLM 基于搜索结果生成最终答案                      │
    │   → "2026年诺贝尔物理学奖得主是..." (citation 含来源) │
    └──────────────────────────────────────────────────────┘
13. should_call_tool → "continue"
14. check_quality → retrieve_quality_hit → END
```

---

## 6. 实施步骤（分阶段）

### Phase 1: 基础设施（2-3天）

| 步骤 | 文件 | 内容 |
|------|------|------|
| 1.1 | `config/mcp_config.py` | MCP 配置类，读取环境变量 |
| 1.2 | `service/MCP/mcp_client.py` | MCPClient 核心实现（JSON-RPC + stdio） |
| 1.3 | `service/MCP/mcp_tool_registry.py` | 工具注册表，MCP schema → LangChain Tool 转换 |
| 1.4 | 测试脚本 | 独立测试 MCP Client 连接 web_search server |

### Phase 2: LangGraph 集成（2-3天）

| 步骤 | 文件 | 内容 |
|------|------|------|
| 2.1 | `state.py` 修改 | 新增 `available_tools`, `tool_call_count`, `max_tool_calls` |
| 2.2 | `node/execute_tool.py` | 工具执行节点 |
| 2.3 | `node/generate_answer.py` 修改 | 增加 tools 参数，支持 AIMessage.tool_calls 检测 |
| 2.4 | `graph.py` 修改 | 注册 execute_tool 节点 + 条件边 |

### Phase 3: Agent Service 集成（1天）

| 步骤 | 文件 | 内容 |
|------|------|------|
| 3.1 | `api_service/agent_service.py` 修改 | 启动时初始化 MCP registry，传给 graph |
| 3.2 | `config/settings.py` 修改（如需要） | 新增 MCP 相关配置项 |

### Phase 4: 测试与优化（2天）

| 步骤 | 内容 |
|------|------|
| 4.1 | 单元测试：MCPClient 的 JSON-RPC 通信 |
| 4.2 | 集成测试：完整 Agent 流程 + web_search 触发 |
| 4.3 | 边界测试：无工具可用、搜索超时、死循环保护 |
| 4.4 | 前端：展示搜索来源（如果前端期望展示 citation） |

---

## 7. 关键风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| **MCP Server 不稳定** | 子进程崩溃导致工具不可用 | ① 自动重启机制 ② 内置 fallback（如直接调 Tavily API） |
| **tool-calling 死循环** | LLM 不断调用工具，消耗 token | `max_tool_calls=5` 硬限制，超限后强制生成答案 |
| **DashScope 对 tools 参数兼容性** | 阿里云 DashScope API 可能不完全支持 function calling | 先用 qwen-plus 测试，必要时降级为 prompt 注入 |
| **工具调用延迟** | 网络搜索增加 2-5 秒响应时间 | ① 并行调用多个工具 ② 前端增加流式输出提示 |
| **现有流程破坏** | 修改 graph.py 可能影响已有功能 | 所有修改在分支上进行，充分测试后再合并 |

---

## 8. 备选方案（如果 MCP 太重）

如果 MCP 全套协议实现成本过高，可以先做一个简化版：

```
service/MCP/
├── mcp_tool_registry.py   # 保留（接口不变）
├── mcp_client.py           # 简化为直接 HTTP 调用（不通过 MCP 协议）
└── tools/
    └── web_search.py       # 直接调用 Tavily/Brave Search API
```

这种方式跳过 MCP 协议层，直接调搜索 API，开发量减半。等 MCP 生态成熟后再切换。

---

## 9. 待讨论的决策点

1. **Web Search 服务商选择**：Tavily（结构化 + 摘要，付费）vs Brave（免费额度多）vs 自建？
2. **MCP Server 托管方式**：stdio 子进程（本方案）还是独立 HTTP 服务？
3. **DashScope function calling 兼容性**：需要先用 qwen-plus 验证对 `tools` 参数的完整支持
4. **结果 citation 格式**：搜索结果如何在最终答案中标注来源？
5. **是否允许用户手动触发搜索**：前端加一个"联网搜索"开关，还是完全由 LLM 自动决策？

---

## 10. 附录：MCP 消息协议示例

### tools/list 请求
```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
```

### tools/list 响应
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [{
      "name": "web_search",
      "description": "Search the web for real-time information",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": {"type": "string", "description": "Search query"},
          "max_results": {"type": "integer", "default": 5}
        },
        "required": ["query"]
      }
    }]
  }
}
```

### tools/call 请求
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "web_search",
    "arguments": {"query": "2026 Nobel Prize Physics", "max_results": 5}
  }
}
```

### tools/call 响应
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [{
      "type": "text",
      "text": "## 2026 Nobel Prize in Physics\n\n..."
    }]
  }
}
```
