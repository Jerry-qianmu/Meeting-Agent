# Knowledge Agent 集成说明

## 已完成的工作

### 1. API 服务层
- ✅ `api_service/agent_service.py` - Knowledge Agent 服务封装
- ✅ `api_service/embedding_service.py` - Embedding 服务（DashScope）
- ✅ `api_controller/agent_controller.py` - Agent API 控制器
- ✅ `api_controller/__init__.py` - 路由导出

### 2. Agent 核心服务
- ✅ `agents/knowledge/service/retrieval_service.py` - 检索服务（适配 Milvus）

### 3. 配置文件更新
- ✅ `config/settings.py` - 修复类型转换问题

### 4. 路由注册
- ✅ `main.py` - 已注册 Agent 路由 `/api/v1/agent`

---

## 待完成的工作

### 1. 缺失的节点文件

以下节点文件已存在但依赖的服务/模块可能不完整：

| 节点文件 | 依赖 | 状态 |
|---------|------|------|
| `node/query_rewrite.py` | `prompt/query_write_prompt.py` | ✅ 已检查，基本可用 |
| `node/determine_retrieval_strategy.py` | `prompt/retrieval_strategy.py` | ⚠️ 需检查 |
| `node/target_knowledge_or_file.py` | MySQL 查询 | ⚠️ 需适配 |
| `node/doc_retrieval.py` | `service/retrieval_service.py` | ✅ 已创建 |
| `node/light_filter.py` | 阈值过滤 | ⚠️ 需检查 |
| `node/rerank.py` | Rerank 模型 | ⚠️ 需实现 |
| `node/generate_answer.py` | `prompt/generate_answer.py` | ⚠️ 需检查 |
| `node/check_quality.py` | 质量评估 | ⚠️ 需实现 |
| `node/retrieve_quality_hit.py` | 重试决策 | ⚠️ 需实现 |

### 2. 缺失的 Prompt 文件

检查以下 prompt 文件是否存在：

```bash
ls -la backend/agents/knowledge/prompt/
```

需要确认的 prompt：
- `query_write_prompt.py` - 查询重写 prompt
- `retrieval_strategy.py` - 检索策略 prompt
- `generate_answer.py` - 答案生成 prompt
- `query_expansion_prompt.py` - 查询扩展 prompt

### 3. 缺失的 Service 实现

需要实现的服务：
- **Rerank Service** - 文档重排序服务
- **Quality Evaluation Service** - 质量评估服务
- **LLM Generation Service** - 答案生成服务

### 4. API 测试

需要测试的 API 端点：
- `POST /api/v1/agent/chat` - 与 Agent 对话
- `GET /api/v1/agent/status` - 检查 Agent 状态

---

## 快速开始

### 1. 启动后端服务

```bash
cd /mnt/d/Study/Agents/MA/data3/zb/MyAgent/backend
python main.py
```

### 2. 测试 Agent 状态

```bash
curl http://localhost:8000/api/v1/agent/status
```

### 3. 与 Agent 对话

```bash
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "什么是知识图谱？",
    "top_k": 5
  }'
```

---

## 架构说明

```
User Query
    ↓
[query_rewrite] → 查询改写（指代消解）
    ↓
[target_knowledge_base] → 确定目标知识库
    ↓
[target_documents] → 确定目标文档
    ↓
[determine_retrieval_strategy] → 确定检索策略
    ↓
[doc_retrieval] → 向量检索（Milvus）
    ↓
[light_filter] → 轻量过滤
    ↓
[rerank] → 重排序
    ↓
[generate_answer] → 答案生成
    ↓
[check_quality] → 质量评估
    ↓
[retrieve_quality_hit] → 质量决策
    ↓
    ├─ 通过 → 返回答案
    └─ 不通过 → 重试检索
```

---

## 下一步建议

1. **检查并修复缺失的节点**：
   ```bash
   # 检查所有节点文件
   ls -la backend/agents/knowledge/node/
   
   # 检查所有 prompt 文件
   ls -la backend/agents/knowledge/prompt/
   ```

2. **实现缺失的服务**：
   - Rerank 服务（可以使用 DashScope Rerank API）
   - 质量评估服务
   - 答案生成服务

3. **测试 Agent 流程**：
   - 先测试单个节点
   - 再测试完整流程
   - 添加日志和监控

4. **前端集成**：
   - 添加 Agent 聊天界面
   - 展示检索过程和来源

---

## 配置文件

确保 `.env` 文件包含必要的配置：

```env
# DashScope
DASHSCOPE_API_KEY=your_api_key

# RAG 配置
REWRITE_MODEL=qwen3.5-plus
DETERMINE-RETRIEVAL-STRATEGY-MODEL=qwen3.5-plus
RERANK_MODEL=qwen3-vl-rerank
GENERATION_MODEL=qwen3.5-plus
QUALITY_EVAL_MODEL=qwen3.5-plus

# 检索配置
TOP_K=10
RERANK_LIMIT=20
RERANK_FINAL_TOP_K=8
HYBRID_ALPHA=0.7

# 质量评估
QUALITY_SCORE_THRESHOLD=0.6
QUALITY_GROUNDEDNESS_THRESHOLD=0.5
QUALITY_RELEVANCE_THRESHOLD=0.5
QUALITY_MAX_RETRIES=2
```

---

## 文档

- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [DashScope API 文档](https://help.aliyun.com/zh/dashscope/)
- [Milvus 文档](https://milvus.io/docs)
