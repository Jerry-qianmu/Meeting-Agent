# 短期记忆系统（Short-Term Memory）改动记录

> 日期：2026-05-05
> 分支：feature/short-term-memory

---

## 一、需求背景

当前 Agent 工作流无记忆能力，每次对话都是独立的，无法理解上下文。

**目标设计：**
- 设定 token 阈值，当 session 历史消息 token 总量超过阈值时触发压缩
- 压缩方式：LLM 从全部历史消息中提取关键信息，生成摘要（`history_prompt`）
- 缓冲区：保留最近 N 轮原始对话（`messages`）
- 后续节点使用 `history_prompt`（压缩记忆）+ `messages`（缓冲区）联合工作

---

## 二、改动文件清单

### 新建文件（2 个）

| 文件 | 说明 |
|------|------|
| `backend/agents/knowledge/prompt/memory_prompt.py` | 历史对话压缩的 system prompt |
| `backend/agents/knowledge/node/memory_manager.py` | 记忆管理节点（加载历史、判断压缩、维护缓冲区） |

### 修改文件（7 个）

| 文件 | 改动说明 |
|------|----------|
| `backend/agents/knowledge/state.py` | State 新增 `session_id`、`history_prompt` 字段 |
| `backend/config/settings.py` | 新增 3 个 memory 配置项 |
| `backend/agents/knowledge/graph.py` | 图中插入 `memory_manager` 节点，调整启动边 |
| `backend/api_controller/agent_controller.py` | 将 `session_id` 传入 service.invoke() |
| `backend/api_service/agent_service.py` | invoke() 接收 `session_id` 并写入 initial_state |
| `backend/agents/knowledge/node/query_rewrite.py` | 改写逻辑支持 `history_prompt` + 缓冲区联合上下文 |
| `backend/agents/knowledge/node/generate_answer.py` | 答案生成和 fallback 均注入 `history_prompt` |

---

## 三、逐文件改动详情

### 1. `state.py` — State 新增字段

```python
# 新增（Conversation Memory 区块）
session_id: Optional[str]                           # 当前会话 ID（前端传入）
messages: Annotated[List[BaseMessage], add_messages] # 当前轮消息（自动追加，不放历史）
history_messages: List[BaseMessage]                  # 历史缓冲区（最近 N 轮，由 memory_manager 填充）
history_prompt: Optional[str]                       # 压缩后的历史记忆摘要
```

> **关键设计**：`messages` 使用 `add_messages` reducer 只会追加，无法在前面插入历史消息。
> 因此将历史消息放到独立的 `history_messages` 字段，`messages` 只放当前轮。

### 2. `config/settings.py` — 新增配置

```python
# Short-term Memory settings
memory_token_threshold = int(os.getenv("MEMORY_TOKEN_THRESHOLD", 2000))   # 触发压缩的 token 阈值
memory_buffer_rounds = int(os.getenv("MEMORY_BUFFER_ROUNDS", 3))          # 缓冲区保留的最近轮数
memory_compress_model = os.getenv("MEMORY_COMPRESS_MODEL", "deepseek-v4-pro")  # 压缩用模型
```

**.env 对应项：**
```env
MEMORY_TOKEN_THRESHOLD=2000
MEMORY_BUFFER_ROUNDS=3
MEMORY_COMPRESS_MODEL=deepseek-v4-pro
```

### 3. `prompt/memory_prompt.py` — 压缩 Prompt（新建）

定义 `MEMORY_COMPRESS_SYSTEM`，指导 LLM 从长对话中提取：
- 关键信息 / 核心事实
- 用户意图 / 偏好
- 重要实体
- 待办 / 未解决问题

输出格式化为四段结构，便于后续注入 prompt。

### 4. `node/memory_manager.py` — 记忆管理节点（新建 + 重写）

**核心函数：** `memory_manager(state) -> dict`

**流程：**
```
1. 无 session_id → 跳过，返回空
2. 优先读缓存（_session_cache[session_id]），miss 时从 DB 加载
3. 估算 token 总量（中文 1.5/字，英文 0.4/字符）
4. if token <= 阈值:
     history_messages = 全部历史（转 LangChain 消息对象）
     history_prompt = ""
5. if token > 阈值:
     old_messages = 历史[:-N*2]       # 需压缩的部分
     recent_messages = 历史[-N*2:]     # 缓冲区（最近 N 轮）
     history_prompt = LLM.compress(old_messages)
     history_messages = recent_messages
6. 压缩失败降级：截取旧消息最后 3 轮作为 fallback
7. 不修改 messages（messages 只放当前轮）
```

**缓存机制：**
```python
# 模块级缓存
_session_cache: Dict[str, Dict[str, Any]] = {}

# graph 运行时：优先读缓存
cache = get_cache(session_id)
if cache:
    db_messages = cache["db_messages"]  # 命中缓存
else:
    db_messages = _load_db_messages(session_id)  # 读 DB
    update_cache(session_id, db_messages)        # 写入缓存

# controller 保存消息后：追加到缓存
append_to_cache(session_id, [
    {"role": 0, "content": query},
    {"role": 1, "content": answer},
])
```

> **缓存策略**：session 级别内存缓存。首次 graph 运行时从 DB 加载并缓存，
> 后续同 session 的 graph 运行直接读缓存。controller 保存新消息后同步追加到缓存，
> 避免缓存与 DB 不一致。

**辅助函数：**
- `get_cache(session_id)` — 获取缓存
- `update_cache(session_id, db_messages)` — 写入缓存
- `append_to_cache(session_id, new_messages)` — 追加到缓存
- `clear_cache(session_id)` / `clear_all_cache()` — 清除缓存
- `_estimate_tokens(text)` — 粗略 token 估算
- `_format_history_for_compress(messages)` — 格式化 DB 消息为压缩输入
- `_compress_history(history_text, model)` — 调用 DashScope LLM 压缩
- `_db_messages_to_lc(db_messages)` — DB 消息 → LangChain HumanMessage/AIMessage
- `_load_db_messages(session_id)` — 从 DB 加载消息

### 5. `graph.py` — 图结构变更

**变更前：**
```
START → query_rewrite → target_knowledge_base → ...
```

**变更后：**
```
START → memory_manager → query_rewrite → target_knowledge_base → ...
```

**具体改动：**
```python
# 新增 import
from .node.memory_manager import memory_manager

# 新增节点
knowledge_agent_graph.add_node("memory_manager", memory_manager)

# 边变更
- knowledge_agent_graph.add_edge(START, "query_rewrite")
+ knowledge_agent_graph.add_edge(START, "memory_manager")
+ knowledge_agent_graph.add_edge("memory_manager", "query_rewrite")
```

### 6. `agent_controller.py` — 传递 session_id

```python
# 变更前
result = await service.invoke(request.query, config)

# 变更后
result = await service.invoke(
    request.query, 
    config, 
    session_id=request.session_id
)
```

### 7. `agent_service.py` — 接收 session_id

```python
# 方法签名变更
- async def invoke(self, query, config=None, user_id=None)
+ async def invoke(self, query, config=None, user_id=None, session_id=None)

# initial_state 新增
+ "session_id": session_id,
```

### 8. `query_rewrite.py` — 联合记忆改写

**变更前：** 仅用 `messages`（state 中的全部消息）作为历史

**变更后：** 使用 `history_prompt`（压缩摘要）+ `messages`（缓冲区）联合构建上下文

```python
# 构建历史上下文
history_context_parts = []
if history_prompt:
    history_context_parts.append(f"【历史对话摘要】\n{history_prompt}")
if recent_history:
    history_context_parts.append("【近期对话】\n" + recent_lines)
```

### 9. `generate_answer.py` — 答案生成注入记忆

**主流程变更：**
```python
# 新增
history_prompt = state.get("history_prompt", "") or ""
if history_prompt:
    history_section = f"\n\n【历史对话摘要】\n{history_prompt}\n"

user_prompt = f"用户问题：{query}\n{history_section}\n上下文材料：..."
```

**fallback 响应变更：**
```python
# 函数签名变更
- def _create_fallback_response(query: str) -> dict:
+ def _create_fallback_response(query: str, history_prompt: str = "") -> dict:

# 所有调用点同步更新（3 处）
- return _create_fallback_response(query)
+ return _create_fallback_response(query, history_prompt)
```

---

## 四、数据流图

```
前端
 │
 │  POST /agent/chat
 │  { session_id, query, knowledge_base_ids, document_ids }
 ▼
agent_controller.py
 │
 │  service.invoke(query, config, session_id=session_id)
 ▼
agent_service.py
 │
 │  initial_state = { session_id, messages: [HumanMessage(query)], ... }
 ▼
LangGraph 执行
 │
 ▼
┌─────────────────────────────────────────────────────────┐
│  memory_manager 节点                                     │
│                                                          │
│  cache = get_cache(session_id)                           │
│  if cache:                                               │
│    db_messages = cache["db_messages"]    # 命中缓存      │
│  else:                                                   │
│    db_messages = DB.load(session_id)     # 读 DB         │
│    update_cache(session_id, db_messages) # 写入缓存      │
│                                                          │
│  ┌─ token ≤ 阈值 ─────────────────────────────────────┐  │
│  │  history_messages = 全部历史                        │  │
│  │  history_prompt = ""                                │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─ token > 阈值 ─────────────────────────────────────┐  │
│  │  history_prompt = LLM.compress(旧消息)              │  │
│  │  history_messages = 最近 N 轮                       │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  注意：不修改 messages，messages 保持 [current_query]    │
└─────────────────────────────────────────────────────────┘
 │
 │  state.messages = [current_query]  （不变）
 │  state.history_messages = [old1, old2, ...]  （缓冲区）
 │  state.history_prompt = "摘要..."  （压缩记忆）
 ▼
query_rewrite
 │  读 history_messages + history_prompt
 │  联合改写 query
 ▼
target_knowledge_base → target_document → determine_strategy
 ▼
doc_retrieval → light_filter → rerank
 ▼
generate_answer
 │  读 history_prompt
 │  联合 chunks 生成答案
 ▼
check_quality → retrieve_quality_hit → [条件重试/返回]
 ▼
返回 { answer, sources, ... }
 │
 ▼
agent_controller
 │  保存 query + answer 到 DB
 │  append_to_cache(session_id, [query, answer])  # 同步更新缓存
```

---

## 五、配置参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MEMORY_TOKEN_THRESHOLD` | 2000 | 历史消息 token 总量超过此值触发压缩 |
| `MEMORY_BUFFER_ROUNDS` | 3 | 压缩后保留最近几轮原始对话（1轮 = 1 user + 1 assistant） |
| `MEMORY_COMPRESS_MODEL` | deepseek-v4-pro | 历史压缩使用的 LLM 模型 |

---

## 六、V2 修复记录（2026-05-06）

### 问题 1：记忆未生效

**根因：** `messages` 使用 `add_messages` reducer，它只会 **追加（append）**，不能在前面插入。
memory_manager 返回 `{"messages": [old1, old2, ...]}` 后，reducer 将其追加到
initial_state 的 `[current_query]` 之后，变成 `[current_query, old1, old2, ...]`。
query_rewrite 读到的 "历史" 其实是当前 query 在最前面，老消息在后面，顺序完全反了。

**修复：** 新增 `history_messages` 字段存放缓冲区，memory_manager 不再修改 `messages`。
`messages` 只放当前轮（由 initial_state 设置）。

### 问题 2：每次从 DB 读取

**根因：** 无 checkpointer，每次 graph 调用都是全新的，每次都从 DB 加载历史。

**修复：** 在 memory_manager 中添加模块级缓存 `_session_cache`：
- 首次 graph 运行：从 DB 加载 → 写入缓存
- 后续 graph 运行：直接读缓存
- controller 保存新消息后：`append_to_cache()` 同步更新缓存

### 改动文件

| 文件 | V2 改动 |
|------|---------|
| `state.py` | 新增 `history_messages: List[BaseMessage]` |
| `memory_manager.py` | 完全重写：不碰 messages，新增缓存机制 |
| `query_rewrite.py` | 从 `history_messages` 读缓冲区（而非 `messages`） |
| `agent_controller.py` | 保存消息后调用 `append_to_cache()` |

---

## 七、注意事项

1. **DB role 字段是整数**：`_format_history_for_compress` 和 `_db_messages_to_lc` 中用 `role == 0` 判断 user，`role == 1` 判断 assistant
2. **压缩失败降级**：LLM 调用失败时，截取旧消息最后 3 轮原文作为 fallback
3. **session_id 为空兼容**：不传 session_id 时 memory_manager 跳过，不影响原有流程
4. **token 估算粗略**：中文 1.5 token/字，英文 0.4 token/字符，用于阈值判断足够
5. **messages vs history_messages**：`messages` 使用 `add_messages` reducer 只会追加，不能在前面插入历史。历史消息放在独立的 `history_messages` 字段
6. **缓存生命周期**：模块级缓存，进程重启后清空。controller 保存消息后同步追加到缓存
