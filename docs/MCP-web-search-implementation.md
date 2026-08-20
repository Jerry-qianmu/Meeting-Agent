# MCP 联网搜索 — 实现文档

> 项目: MyAgent 知识库管理系统  
> 日期: 2026-05-24  
> 版本: v1.0.0

---

## 1. 实现概览

在 LangGraph Agent 中集成了 MCP (Model Context Protocol) 工具调用能力，第一阶段实现了**联网搜索**（通过 Tavily MCP Server）。

### 核心架构

```
用户问题 → memory_manager → query_rewrite → target_kb → ... → rerank
                                                                    ↓
                                                            generate_answer
                                                           /              \
                                              [无KB结果+联网开关ON]    [有KB结果/开关OFF]
                                                         ↓                    ↓
                                                   LLM+Tool Calling      正常KB回答
                                                         ↓
                                                   LLM返回tool_calls?
                                                    /          \
                                                  YES           NO
                                                   ↓             ↓
                                             execute_tool    生成答案
                                              (MCP调用)          ↓
                                                   ↓        check_quality
                                                   ↓             ↓
                                            generate_answer  → END
                                            (ReAct回环)
```

### 数据流（web_search 被触发时）

```
1. 用户: "2026年诺贝尔奖得主是谁？"  [web_search_enabled=true, 无KB结果]
2. generate_answer: LLM+tool_calls → AIMessage(tool_calls=[web_search])
3. should_call_tool → "call_tool"
4. execute_tool: MCP Client → tavily-mcp 子进程 → tools/call
5. 结果: ToolMessage("搜索结果...")
6. generate_answer (ReAct): 基于搜索结果生成最终答案
7. should_call_tool → "continue"
8. check_quality → retrieve_quality_hit → END
```

---

## 2. 修改文件清单

### 新增文件 (5个)

| 文件 | 说明 |
|------|------|
| `backend/config/mcp_config.py` | MCP 配置管理，读取 TAVILY_API_KEY 等 |
| `backend/service/MCP/__init__.py` | MCP 模块包初始化 |
| `backend/service/MCP/mcp_client.py` | JSON-RPC stdio MCP 客户端（280行） |
| `backend/service/MCP/mcp_tool_registry.py` | 工具注册表，MCP→LangChain 转换（350行） |
| `backend/agents/knowledge/node/execute_tool.py` | MCP 工具执行节点（120行） |

### 修改文件 (7个)

| 文件 | 修改内容 |
|------|---------|
| `backend/config/settings.py` | 新增 4 行: tavily_api_key, MCP 超时配置 |
| `backend/agents/knowledge/state.py` | 新增 4 字段: available_tools, tool_call_count, max_tool_calls, web_search_enabled |
| `backend/agents/knowledge/node/generate_answer.py` | 完全重写: 三路径(ABQ/ToolCalling/ReAct) + Tool Calling 支持 (~700行) |
| `backend/agents/knowledge/graph.py` | 新增 execute_tool 节点 + should_call_tool 条件边 |
| `backend/api_service/agent_service.py` | 新增 _ensure_mcp_initialized(), 传递 web_search_enabled |
| `backend/api_controller/agent_controller.py` | ChatRequest 新增 web_search_enabled 字段 |
| `frontend/src/views/AgentChatView.vue` | 新增联网搜索开关按钮 + 传递参数 |
| `frontend/src/style.css` | 新增 agent-web-search-btn 样式 (~30行) |

---

## 3. 关键设计决策

### 3.1 为什么用 Tool-Calling 而不是硬编码路由？

硬编码路由（如新增 `web_search` 节点+条件边）的问题：
- 需要预判"什么时候该搜索"——规则难以覆盖所有场景
- 无法处理"搜索后再搜索"的复杂场景

Tool-Calling 的优势：
- LLM 自主决定何时调用工具（更智能）
- 支持连续多轮工具调用（搜索→分析→再搜索）
- 扩展新工具只需注册，不用改图结构
- 与 LangGraph ReAct 模式完全兼容

### 3.2 为什么用 MCP 而不是直接调 Tavily API？

| 对比维度 | 直接调 Tavily API | 通过 MCP |
|---------|-----------------|---------|
| 标准化 | 每个工具有自己的 API | 统一 JSON-RPC 协议 |
| 扩展性 | 每个工具单独写客户端 | 只需注册新 MCP Server |
| 工具发现 | 需要手动声明 schema | 自动从 Server 获取 |
| 生态 | 孤立的 | 可复用社区 MCP Server |
| 复杂度 | 简单（单工具时） | 稍高（但长期收益大） |

### 3.3 为什么 stdio 而不是 HTTP？

- stdio: 子进程通信，零网络延迟，无需端口管理
- HTTP: 需要额外管理端口和网络配置
- 本地部署场景 stdio 是最佳选择

### 3.4 为什么延迟初始化 MCP？

只有用户点击"联网搜索"开关时才启动 MCP Server：
- 避免启动延迟
- 不浪费资源（如果用户不用搜索）
- 优雅降级：MCP 不可用时自动 fallback 到模型自身知识

---

## 4. 配置指南

### 4.1 获取 Tavily API Key

1. 访问 https://tavily.com/
2. 注册账号（免费额度 1000 次/月）
3. 获取 API Key: `tvly-xxxxxxxxxxxxxxxxxxxxxxxx`

### 4.2 设置环境变量

在 `backend/.env` 文件中添加：

```bash
# Tavily MCP Web Search
TAVILY_API_KEY=tvly-your-api-key-here

# MCP 可选配置（使用默认值即可）
MCP_TOOL_CALL_TIMEOUT=30
MCP_SERVER_STARTUP_TIMEOUT=15
MCP_MAX_TOOL_CALLS=5
```

### 4.3 安装 tavily-mcp

```bash
# 全局安装（推荐）
npm install -g tavily-mcp

# 或者让 npx 自动下载（首次调用稍慢）
# 不需要手动安装，npx -y tavily-mcp 会自动处理
```

### 4.4 验证

```bash
# 测试 MCP Server 是否正常启动
TAVILY_API_KEY=tvly-xxx npx -y tavily-mcp &
# 应该看到 "Tavily MCP Server running on stdio"

# 测试后端
cd backend
python -c "
import asyncio
from service.MCP import get_mcp_registry

async def test():
    registry = await get_mcp_registry()
    print(f'工具数量: {registry.tool_count}')
    print(f'工具名称: {registry.get_tool_names()}')
    result = await registry.call_tool(
        'mcp__web_search__tavily_search',
        {'query': 'test', 'max_results': 1}
    )
    print(f'搜索结果: {result[:200]}...')
    await registry.shutdown()

asyncio.run(test())
"
```

---

## 5. 前端使用

### 界面

对话框底部新增"联网搜索"按钮，与"知识库"选择器并列：

```
[Shift+Enter 换行] [🌐 知识库 (0)] [🌍 联网搜索]        [发送]
```

- **未激活**：灰色边框，显示"联网搜索"
- **已激活**：绿色边框，显示"联网搜索 开"
- **发送中**：按钮禁用（避免状态变更）

### 行为

1. 用户点击"联网搜索"按钮激活
2. 输入问题发送
3. 如果知识库检索无结果：
   - 联网搜索**开** → Agent 自动调用 web_search 获取信息
   - 联网搜索**关** → Agent 使用模型自身知识回答
4. 如果知识库检索有结果 → 直接基于知识库回答（不会触发联网搜索）

---

## 6. 故障排查

### MCP Server 启动失败

```
错误: "找不到命令 'npx'"
解决: 安装 Node.js (>=18): apt install nodejs npm
```

```
错误: "MCP Server 初始化超时"
原因: npx 首次下载 tavily-mcp 速度慢
解决: npm install -g tavily-mcp 预安装
```

### 搜索结果为空

```
原因: TAVILY_API_KEY 未设置或无效
检查: echo $TAVILY_API_KEY
```

### 联网搜索不触发

检查点：
1. `.env` 中 TAVILY_API_KEY 是否正确
2. 前端是否点击了联网搜索按钮（绿色高亮）
3. 知识库是否有相关结果（有KB结果时不会调用搜索）
4. 查看后端日志: `[GenerateAnswer] Tool-calling 模式`

### 死循环保护

如果 LLM 反复调用工具，`max_tool_calls=5` 会在第 5 次后强制停止，不再传 tools 参数。

### DashScope tools 兼容性

当前 uses `deepseek-v4-pro` 模型。如果模型不支持 `tools` 参数，降级为普通 prompt 回答。日志会显示: `[GenerateAnswer] Tool-calling 异常`

---

## 7. 扩展指南：添加新 MCP 工具

添加一个新工具（如计算器）只需 2 步：

### 步骤 1: 修改 `config/mcp_config.py`

```python
@staticmethod
def get_servers() -> List[MCPServerConfig]:
    servers = []
    
    # ... web_search 配置 ...
    
    # 新增：计算器
    servers.append(MCPServerConfig(
        name="calculator",
        command=["python", "-m", "mcp_calculator"],
        enabled=True,
        description="数学计算工具"
    ))
    
    return servers
```

### 步骤 2: 重启后端

```bash
# 新工具会在首次使用时自动注册
# AgentService._ensure_mcp_initialized() 自动发现
```

无需修改 graph.py、state.py、generate_answer.py 或 execute_tool.py。

---

## 8. 兼容性说明

| 组件 | 版本要求 |
|------|---------|
| Python | >=3.10 |
| Node.js | >=18 (仅 MCP Server) |
| LangGraph | >=0.2.0 |
| langchain-core | >=0.3.0 |
| DashScope | >=1.16.0 |
| FastAPI | >=0.100 |
| pydantic | >=2.0 |

### 不兼容说明

- **不使用 MCP 时完全不影响现有功能**：`web_search_enabled=False` 时走原有代码路径
- **TAVILY_API_KEY 未设置时优雅降级**：MCP 初始化失败但不影响应用启动
- **npx 不可用时**：后端正常启动，但联网搜索不可用（前端开关仍可点击，只是后端会 fallback）

---

## 9. 文件完整路径索引

```
D:\Study\Agents\MA\data3\zb\MyAgent\
├── backend/
│   ├── config/
│   │   ├── settings.py                    ← 修改：新增 MCP 配置
│   │   └── mcp_config.py                  ← 新增：MCP Server 列表
│   ├── service/
│   │   └── MCP/
│   │       ├── __init__.py                ← 新增：模块导出
│   │       ├── mcp_client.py              ← 新增：JSON-RPC stdio 客户端
│   │       └── mcp_tool_registry.py       ← 新增：工具注册表
│   ├── agents/
│   │   └── knowledge/
│   │       ├── state.py                   ← 修改：新增 4 字段
│   │       ├── graph.py                   ← 修改：新增 execute_tool 节点
│   │       └── node/
│   │           ├── generate_answer.py     ← 修改：三路径 + Tool Calling
│   │           └── execute_tool.py        ← 新增：MCP 工具执行节点
│   ├── api_service/
│   │   └── agent_service.py              ← 修改：MCP 延迟初始化
│   └── api_controller/
│       └── agent_controller.py            ← 修改：web_search_enabled
└── frontend/
    └── src/
        ├── views/
        │   └── AgentChatView.vue           ← 修改：联网搜索开关
        └── style.css                       ← 修改：按钮样式
```
