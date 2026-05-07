# Knowledge Agent 集成指南

## ✅ 已完成的工作

### 1. API 服务层
- ✅ `api_service/agent_service.py` - Knowledge Agent 服务封装
  - 使用现有的 `service/retrieval_service.py`
  - 使用现有的 `service/embedding_service.py`
  - 支持配置参数传递

### 2. API 控制器
- ✅ `api_controller/agent_controller.py` - Agent API 控制器
  - `POST /api/v1/agent/chat` - 与 Agent 对话
  - `GET /api/v1/agent/status` - 检查 Agent 状态
  - `POST /api/v1/agent/query-expand` - 查询扩展（测试用）
  - `POST /api/v1/agent/rewrite` - 查询重写（测试用）

### 3. 路由注册
- ✅ `main.py` - 已注册 Agent 路由
- ✅ `api_controller/__init__.py` - 路由导出

### 4. 配置修复
- ✅ `config/settings.py` - 修复类型转换问题
  - `light_filter_threshold` → float
  - `group_size` → int
  - `rrf_k` → int
  - `hybrid_alpha` → float
  - `max_context_tokens` → int
  - `rerank_limit` → int
  - `rerank_final_top_k` → int
  - `use_text_match_filter` → bool

### 5. 模块初始化
- ✅ `agents/__init__.py`
- ✅ `agents/knowledge/__init__.py`

---

## 📁 现有 Service 文件

你的项目已有以下 service（位于 `backend/service/`）：

| 文件 | 功能 | 说明 |
|------|------|------|
| `retrieval_service.py` | 混合检索 | vector/keyword/hybrid 检索，RRF 融合 |
| `embedding_service.py` | Embedding | DashScope text-embedding-v4 |
| `parse.py` | 文档解析 | PDF/TXT/MD 解析 |

---

## 🔧 Agent 节点状态

### 已检查的节点

| 节点 | 文件 | 依赖 | 状态 |
|------|------|------|------|
| query_rewrite | `node/query_rewrite.py` | prompt/query_write_prompt.py | ✅ 基本可用 |
| target_kb/docs | `node/target_knowledge_or_file.py` | 无 | ✅ 从 state 获取参数 |
| doc_retrieval | `node/doc_retrieval.py` | service/retrieval_service.py | ✅ 使用现有 service |
| graph | `graph.py` | 所有节点 | ⚠️ 需测试 |

### 待检查的节点

需要确认以下节点是否有缺失依赖：

- `node/determine_retrieval_strategy.py`
- `node/light_filter.py`
- `node/rerank.py`
- `node/generate_answer.py`
- `node/check_quality.py`
- `node/retrieve_quality_hit.py`

---

## 🚀 快速测试

### 1. 启动后端

```bash
cd /mnt/d/Study/Agents/MA/data3/zb/MyAgent/backend
python main.py
```

### 2. 检查 Agent 状态

```bash
curl http://localhost:8000/api/v1/agent/status
```

预期响应：
```json
{
  "status": "ready",
  "graph_initialized": true
}
```

### 3. 与 Agent 对话

```bash
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "什么是知识库？",
    "top_k": 5
  }'
```

---

## ⚠️ 可能的问题

### 1. 缺少 langgraph 依赖

如果启动时报错 `ModuleNotFoundError: No module named 'langgraph'`，需要安装：

```bash
pip install langgraph langchain-core
```

### 2. 缺少 DashScope 依赖

```bash
pip install dashscope
```

### 3. 环境变量缺失

确保 `.env` 文件包含：

```env
# DashScope
DASHSCOPE_API_KEY=your_api_key

# RAG 配置
REWRITE_MODEL=qwen3.5-plus
GENERATION_MODEL=qwen3.5-plus
QUALITY_EVAL_MODEL=qwen3.5-plus

TOP_K=10
RERANK_LIMIT=20
RERANK_FINAL_TOP_K=8
```

---

## 📋 下一步工作

### 1. 测试 Agent 图初始化

确认所有节点都能正常导入：

```bash
cd /mnt/d/Study/Agents/MA/data3/zb/MyAgent/backend
python -c "from agents.knowledge.graph import create_knowledge_agent_graph; g = create_knowledge_agent_graph(); print('Success')"
```

### 2. 检查缺失的 Prompt 文件

```bash
ls -la backend/agents/knowledge/prompt/
```

确认以下文件存在：
- `query_write_prompt.py`
- `retrieval_strategy.py`
- `generate_answer.py`

### 3. 实现缺失的服务

如果节点报错缺少服务，需要创建：
- `service/rerank_service.py` - Rerank 服务
- `service/quality_service.py` - 质量评估服务
- `service/generation_service.py` - 答案生成服务

### 4. 前端集成

创建聊天界面，调用 `POST /api/v1/agent/chat`

---

## 📊 Agent 流程图

```
START
  ↓
query_rewrite → 查询重写（指代消解）
  ↓
target_knowledge_base → 确定目标知识库
  ↓
target_documents → 确定目标文档
  ↓
determine_retrieval_strategy → 确定检索策略
  ↓
retrieve_chunks → 向量检索（Milvus）
  ↓
filter_chunks → 轻量过滤
  ↓
chunk_rerank → 重排序
  ↓
generate_answer → 答案生成
  ↓
check_quality → 质量评估
  ↓
retrieve_quality_hit → 质量决策
  ↓
    ├─ 通过 → END (返回答案)
    └─ 不通过 → 回到 retrieve_chunks (重试)
```

---

## 📝 注意事项

1. **UUID 格式**：所有 UUID 字段使用字符串格式（CHAR(36)）
2. **JSON 序列化**：使用 `json.dumps()` 而非 `str()`
3. **事务提交**：查询后调用 `conn.commit()`
4. **DashScope 限制**：batch_size ≤ 10
5. **Milvus 类型**：自定义字段为 VARCHAR，int/float 需转字符串

---

## 🔗 相关文档

- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [DashScope API](https://help.aliyun.com/zh/dashscope/)
- [Milvus 文档](https://milvus.io/docs)
