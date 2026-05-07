# Knowledge Agent 持久化层函数设计文档

> **版本**: v1.0  
> **最后更新**: 2026-04-28  
> **说明**: 详细函数接口设计，不含具体代码

---

## 目录

1. [Repository 层函数设计](#1-repository-层函数设计)
2. [Service 层函数设计](#2-service-层函数设计)
3. [工作链路函数执行流程](#3-工作链路函数执行流程)
4. [函数调用关系图](#4-函数调用关系图)

---

## 1. Repository 层函数设计

### 1.1 SessionRepository（会话管理）

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `create_session` | `user_id: bytes`, `title: str` | `session_uuid: bytes` | 创建新会话，返回 session UUID |
| `get_session` | `session_uuid: bytes` | `Dict | None` | 获取会话详情 |
| `get_user_sessions` | `user_id: bytes`, `page: int`, `page_size: int` | `List[Dict]` | 获取用户会话列表（分页） |
| `update_session_title` | `session_uuid: bytes`, `title: str` | `int` | 更新会话标题（返回影响行数） |
| `delete_session` | `session_uuid: bytes` | `int` | 删除会话（软删除） |
| `count_user_sessions` | `user_id: bytes` | `int` | 统计用户会话总数 |

### 1.2 MessageRepository（消息管理）

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `add_message` | `session_uuid: bytes`, `role: int`, `content: str`, `metadata: Dict` | `message_uuid: bytes` | 添加消息（role: 0=user, 1=assistant, 2=system） |
| `get_messages` | `session_uuid: bytes`, `limit: int` | `List[Dict]` | 获取会话消息历史 |
| `get_message` | `message_uuid: bytes` | `Dict | None` | 获取单条消息详情 |
| `update_message` | `message_uuid: bytes`, `content: str` | `int` | 更新消息内容 |
| `delete_message` | `message_uuid: bytes` | `int` | 删除消息 |
| `count_session_messages` | `session_uuid: bytes` | `int` | 统计会话消息数 |

### 1.3 MemoryRepository（记忆系统）

#### 1.3.1 短期记忆

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `insert_short_term_memory` | `session_uuid: bytes`, `user_id: bytes`, `query_summary: str`, `answer_summary: str`, `entities: Dict`, `key_facts: Dict`, `message_uuid: bytes` | `int` | 插入短期记忆记录 |
| `get_short_term_memories` | `session_uuid: bytes`, `limit: int` | `List[Dict]` | 获取会话的短期记忆列表 |
| `get_recent_memory` | `session_uuid: bytes`, `n: int` | `List[Dict]` | 获取最近 N 条短期记忆 |
| `update_memory_access` | `memory_id: int` | `int` | 更新记忆访问次数 |
| `cleanup_expired_memories` | `None` | `int` | 清理过期记忆（定时任务） |
| `delete_session_memories` | `session_uuid: bytes` | `int` | 删除会话的所有短期记忆 |

#### 1.3.2 长期记忆

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `insert_long_term_memory` | `user_id: bytes`, `memory_type: str`, `category: str`, `title: str`, `content: str`, `tags: List`, `importance_score: float`, `source_type: str`, `source_uuid: bytes` | `int` | 插入长期记忆 |
| `get_long_term_memory` | `memory_id: int` | `Dict | None` | 获取单条长期记忆 |
| `search_long_term_memories` | `user_id: bytes`, `query: str`, `memory_type: str`, `top_k: int` | `List[Dict]` | 搜索长期记忆（按相关性和重要性） |
| `get_user_memories` | `user_id: bytes`, `memory_type: str`, `page: int`, `page_size: int` | `List[Dict]` | 获取用户的长期记忆列表 |
| `update_memory_importance` | `memory_id: int`, `importance_score: float` | `int` | 更新记忆重要性分数 |
| `update_memory_access` | `memory_id: int` | `int` | 更新记忆访问次数 |
| `delete_memory` | `memory_id: int` | `int` | 删除长期记忆 |
| `merge_similar_memories` | `user_id: bytes`, `threshold: float` | `int` | 合并相似记忆（去重） |

### 1.4 RetrievalLogRepository（检索日志）

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `create_retrieval_log` | `session_uuid: bytes`, `message_uuid: bytes`, `query: str`, `rewritten_query: str`, `retrieval_strategy: str`, `top_k: int` | `retrieval_id: int` | 创建检索日志记录 |
| `add_retrieval_result` | `retrieval_id: int`, `chunk_id: str`, `score: float`, `rerank_score: float` | `int` | 添加检索结果（多条 chunk） |
| `update_retrieval_stats` | `retrieval_id: int`, `chunks_before_filter: int`, `chunks_after_filter: int`, `rerank_used: bool` | `int` | 更新检索统计信息 |
| `update_quality_trigger` | `retrieval_id: int`, `quality_triggered: bool`, `retry_count: int` | `int` | 更新质量重试标记 |
| `update_final_answer` | `retrieval_id: int`, `final_answer_length: int` | `int` | 更新最终答案长度 |
| `get_retrieval_log` | `retrieval_id: int` | `Dict | None` | 获取单次检索日志 |
| `get_session_retrieval_logs` | `session_uuid: bytes`, `limit: int` | `List[Dict]` | 获取会话的检索历史 |
| `get_retrieval_stats` | `session_uuid: bytes`, `start_date: str`, `end_date: str` | `Dict` | 获取统计信息（平均检索时间、平均 chunk 数等） |

### 1.5 QualityLogRepository（质量评估日志）

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `insert_quality_log` | `session_uuid: bytes`, `message_uuid: bytes`, `query: str`, `rewritten_query: str`, `retrieval_strategy: str`, `chunks_retrieved: int`, `answer: str`, `answer_length: int`, `context_tokens: int`, `quality_score: float`, `relevance_score: float`, `groundedness_score: float`, `completeness_score: float`, `factuality_score: float`, `quality_passed: bool`, `should_retry: bool`, `retry_count: int`, `fallback_used: bool`, `issues: List`, `total_duration_ms: int`, `retrieval_duration_ms: int`, `generation_duration_ms: int`, `quality_check_duration_ms: int` | `int` | 插入质量评估记录 |
| `get_quality_log` | `quality_id: int` | `Dict | None` | 获取单条质量日志 |
| `get_session_quality_logs` | `session_uuid: bytes`, `limit: int` | `List[Dict]` | 获取会话的质量评估历史 |
| `get_quality_statistics` | `start_date: str`, `end_date: str` | `Dict` | 获取质量统计数据（通过率、平均分等） |
| `get_failed_queries` | `limit: int` | `List[Dict]` | 获取质量未通过的查询（用于分析优化） |
| `get_low_quality_by_strategy` | `retrieval_strategy: str` | `List[Dict]` | 按检索策略统计低质量查询 |
| `get_avg_quality_by_date` | `days: int` | `List[Dict]` | 按日期统计平均质量分数 |

### 1.6 FeedbackRepository（用户反馈）

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `add_feedback` | `message_uuid: bytes`, `rating: int`, `helpful: bool`, `feedback_type: str`, `comment: str`, `feedback_details: Dict` | `int` | 添加用户反馈 |
| `get_feedback` | `message_uuid: bytes` | `Dict | None` | 获取消息的反馈 |
| `get_user_feedback` | `user_id: bytes`, `page: int`, `page_size: int` | `List[Dict]` | 获取用户的反馈列表 |
| `update_feedback` | `feedback_id: int`, `rating: int`, `comment: str` | `int` | 更新反馈 |
| `delete_feedback` | `feedback_id: int` | `int` | 删除反馈 |
| `get_feedback_statistics` | `start_date: str`, `end_date: str` | `Dict` | 获取反馈统计（平均分、反馈率等） |

---

## 2. Service 层函数设计

### 2.1 SessionService（会话服务）

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `create_new_session` | `user_id: bytes`, `title: str = ""` | `session_uuid: bytes` | 创建新会话（调用 Repository） |
| `get_session_info` | `session_uuid: bytes` | `Dict` | 获取会话信息（含消息数） |
| `get_user_session_list` | `user_id: bytes`, `page: int = 1`, `page_size: int = 20` | `Dict` | 获取用户会话列表（分页） |
| `rename_session` | `session_uuid: bytes`, `title: str` | `bool` | 重命名会话 |
| `delete_session_with_messages` | `session_uuid: bytes` | `bool` | 删除会话及其所有消息 |
| `get_conversation_history` | `session_uuid: bytes`, `limit: int = 50` | `List[Dict]` | 获取对话历史（用于前端展示） |

### 2.2 MemoryService（记忆服务）

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `extract_short_term_memory` | `session_uuid: bytes`, `user_id: bytes`, `query: str`, `answer: str`, `message_uuid: bytes` | `Dict` | 从对话中提取短期记忆（调用 LLM） |
| `save_short_term_memory` | `session_uuid: bytes`, `user_id: bytes`, `memory_data: Dict` | `bool` | 保存短期记忆到数据库 |
| `retrieve_short_term_memories` | `session_uuid: bytes`, `limit: int = 10` | `List[Dict]` | 检索当前会话的短期记忆（用于上下文） |
| `trigger_long_term_memory` | `user_id: bytes`, `query: str`, `answer: str`, `feedback: Dict` | `bool` | 判断是否需要创建长期记忆（规则引擎） |
| `create_long_term_memory` | `user_id: bytes`, `memory_type: str`, `category: str`, `title: str`, `content: str`, `tags: List`, `importance_score: float`, `source_type: str`, `source_uuid: bytes` | `bool` | 创建长期记忆 |
| `retrieve_long_term_memories` | `user_id: bytes`, `query: str`, `memory_type: str`, `top_k: int = 5` | `List[Dict]` | 检索长期记忆（用于增强回答） |
| `update_memory_importance` | `memory_id: int`, `increase: bool = True` | `bool` | 更新记忆重要性（根据访问频率） |
| `cleanup_expired_memories` | `None` | `int` | 定时清理过期短期记忆 |
| `merge_similar_memories` | `user_id: bytes`, `threshold: float = 0.8` | `int` | 合并相似长期记忆（去重） |

### 2.3 RetrievalLogService（检索日志服务）

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `log_retrieval_start` | `session_uuid: bytes`, `message_uuid: bytes`, `query: str`, `rewritten_query: str`, `retrieval_strategy: str`, `top_k: int` | `retrieval_id: int` | 记录检索开始（创建日志） |
| `log_retrieval_results` | `retrieval_id: int`, `chunks: List[Dict]` | `bool` | 记录检索到的 chunks |
| `log_filter_stats` | `retrieval_id: int`, `chunks_before: int`, `chunks_after: int` | `bool` | 记录过滤统计 |
| `log_rerank_result` | `retrieval_id: int`, `rerank_used: bool`, `rerank_model: str` | `bool` | 记录重排结果 |
| `log_quality_retry` | `retrieval_id: int`, `quality_triggered: bool`, `retry_count: int` | `bool` | 记录质量重试 |
| `log_final_answer` | `retrieval_id: int`, `answer_length: int`, `duration_ms: int` | `bool` | 记录最终答案 |
| `get_retrieval_history` | `session_uuid: bytes`, `limit: int = 20` | `List[Dict]` | 获取检索历史 |
| `get_retrieval_analytics` | `session_uuid: bytes`, `start_date: str`, `end_date: str` | `Dict` | 获取检索分析数据 |

### 2.4 QualityLogService（质量日志服务）

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `log_quality_assessment` | `session_uuid: bytes`, `message_uuid: bytes`, `query: str`, `rewritten_query: str`, `retrieval_strategy: str`, `chunks_retrieved: int`, `answer: str`, `answer_length: int`, `context_tokens: int`, `quality_score: float`, `breakdown: Dict`, `issues: List`, `passed: bool`, `should_retry: bool`, `retry_count: int`, `fallback_used: bool`, `durations: Dict` | `bool` | 记录完整的质量评估结果 |
| `get_quality_history` | `session_uuid: bytes`, `limit: int = 20` | `List[Dict]` | 获取质量评估历史 |
| `get_quality_statistics` | `start_date: str`, `end_date: str` | `Dict` | 获取质量统计数据 |
| `get_failed_queries` | `limit: int = 100` | `List[Dict]` | 获取失败查询用于分析 |
| `analyze_quality_trends` | `days: int = 30` | `Dict` | 分析质量趋势（按日期） |
| `compare_strategies` | `None` | `Dict` | 对比不同检索策略的质量表现 |
| `get_low_quality_patterns` | `min_count: int = 10` | `List[Dict]` | 识别低质量模式（常见问题类型） |

### 2.5 FeedbackService（反馈服务）

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `submit_feedback` | `user_id: bytes`, `message_uuid: bytes`, `rating: int`, `helpful: bool`, `feedback_type: str`, `comment: str`, `feedback_details: Dict` | `bool` | 提交用户反馈 |
| `get_feedback_for_message` | `message_uuid: bytes` | `Dict | None` | 获取消息的反馈 |
| `get_user_feedback_history` | `user_id: bytes`, `page: int`, `page_size: int` | `Dict` | 获取用户反馈历史 |
| `analyze_feedback_trends` | `start_date: str`, `end_date: str` | `Dict` | 分析反馈趋势 |
| `get_feedback_by_rating` | `rating: int`, `limit: int` | `List[Dict]` | 获取特定评分的反馈 |
| `export_feedback_report` | `start_date: str`, `end_date: str`, `format: str` | `bytes` | 导出反馈报告（CSV/Excel） |

---

## 3. 工作链路函数执行流程

### 3.1 完整问答链路

```
用户提问
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. SessionService.get_conversation_history()                │
│    - 获取会话历史（用于上下文）                               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. MemoryService.retrieve_short_term_memories()             │
│    - 检索短期记忆（指代消解）                                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. MemoryService.retrieve_long_term_memories()              │
│    - 检索长期记忆（用户偏好）                                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ === 进入 Knowledge Agent Graph ===                          │
│                                                              │
│ Node: query_rewrite                                          │
│   └─ RetrievalLogService.log_retrieval_start()              │
│                                                              │
│ Node: doc_retrieval                                          │
│   └─ RetrievalLogService.log_retrieval_results()            │
│                                                              │
│ Node: light_filter                                           │
│   └─ RetrievalLogService.log_filter_stats()                 │
│                                                              │
│ Node: chunk_rerank                                           │
│   └─ RetrievalLogService.log_rerank_result()                │
│                                                              │
│ Node: generate_answer                                        │
│                                                              │
│ Node: check_quality                                          │
│   └─ 调用 quality_control                                    │
│                                                              │
│ Node: retrieve_quality_hit                                   │
│   ├─ 如果 passed=True                                        │
│   │   └─ RetrievalLogService.log_final_answer()             │
│   │   └─ QualityLogService.log_quality_assessment()         │
│   │   └─ 返回答案                                            │
│   │                                                          │
│   └─ 如果 should_retry=True                                  │
│       └─ RetrievalLogService.log_quality_retry()            │
│       └─ 回到 doc_retrieval                                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. SessionService.add_message() (user)                      │
│    - 记录用户问题                                            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. SessionService.add_message() (assistant)                 │
│    - 记录助手回答                                            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. MemoryService.extract_short_term_memory()                │
│    - 提取短期记忆                                            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. MemoryService.save_short_term_memory()                   │
│    - 保存短期记忆                                            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. MemoryService.trigger_long_term_memory()                 │
│    - 判断是否创建长期记忆                                     │
│    └─ 如果触发 → MemoryService.create_long_term_memory()    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
完成
```

### 3.2 质量评估详细流程

```
generate_answer 输出答案
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ check_quality Node                                           │
│   └─ quality_control()                                      │
│       │                                                      │
│       ├─ 规则评估                                            │
│       │   └─ _rule_based_quality_check()                    │
│       │       ├─ 检查答案长度                                │
│       │       ├─ 检查引用来源                                │
│       │       ├─ 检查 metadata 标志                          │
│       │       └─ 返回 rule_based_decision                   │
│       │                                                      │
│       ├─ 如果规则评估通过 → 返回                             │
│       │                                                      │
│       └─ 如果规则评估不通过                                   │
│           ├─ LLM 评估                                         │
│           │   └─ _llm_quality_evaluation()                  │
│           │       ├─ 构建评估 prompt                         │
│           │       ├─ 调用 LLM                                │
│           │       └─ 解析 JSON 结果                          │
│           │                                                  │
│           ├─ 合并评估结果                                    │
│           │   └─ _merge_decisions()                         │
│           │                                                  │
│           └─ 决定重试策略                                    │
│               └─ _determine_retry_strategy()                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ QualityLogService.log_quality_assessment()                  │
│   - 插入 quality_log 表                                      │
│   - 包含：query, answer, scores, issues, durations 等        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ retrieve_quality_hit Node                                    │
│   ├─ 如果 passed=True                                        │
│   │   └─ 返回答案                                            │
│   │                                                          │
│   ├─ 如果 fallback_used=True                                 │
│   │   └─ 返回 fallback 答案                                  │
│   │                                                          │
│   └─ 如果 should_retry=True                                  │
│       ├─ 更新 retry_count                                    │
│       └─ 回到 doc_retrieval                                  │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 记忆系统触发流程

```
用户提问 → 助手回答
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 短期记忆提取                                                 │
│   ├─ MemoryService.extract_short_term_memory()              │
│   │   ├─ 调用 LLM 提取 query_summary                         │
│   │   ├─ 调用 LLM 提取 answer_summary                         │
│   │   ├─ 调用 LLM 提取 entities                              │
│   │   └─ 调用 LLM 提取 key_facts                             │
│   │                                                          │
│   └─ MemoryService.save_short_term_memory()                 │
│       └─ MemoryRepository.insert_short_term_memory()        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 长期记忆触发（规则引擎）                                      │
│   ├─ MemoryService.trigger_long_term_memory()               │
│   │   ├─ 规则 1: 用户明确表达偏好 → memory_type="preference"  │
│   │   ├─ 规则 2: 同一主题多次询问 → 更新 importance           │
│   │   ├─ 规则 3: 用户标记「重要」→ memory_type="fact"         │
│   │   └─ 规则 4: 负面反馈 → 记录不喜欢的主题                 │
│   │                                                          │
│   └─ 如果触发创建 → MemoryService.create_long_term_memory() │
│       └─ MemoryRepository.insert_long_term_memory()         │
└─────────────────────────────────────────────────────────────┘
```

### 3.4 用户反馈流程

```
用户收到答案
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 用户提交反馈                                                 │
│   └─ FeedbackService.submit_feedback()                      │
│       ├─ 验证 message_uuid                                   │
│       ├─ 检查是否已反馈（避免重复）                          │
│       └─ FeedbackRepository.add_feedback()                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 反馈触发长期记忆（可选）                                      │
│   └─ 如果反馈为负面 → 触发 MemoryService.trigger_long_term_memory() │
│       └─ 记录用户不喜欢的主题/方式                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 函数调用关系图

### 4.1 层级关系

```
┌─────────────────────────────────────────────────────────────┐
│                      Controller/API 层                        │
│  (Flask/FastAPI endpoints)                                   │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                      Service 层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │SessionService│  │MemoryService │  │QualityLogService │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │FeedbackService│ │RetrievalLogService│                   │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Repository 层                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │SessionRepo   │  │MemoryRepo    │  │QualityLogRepo    │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │FeedbackRepo  │  │RetrievalLogRepo│                      │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                     MySQL Client                             │
│  (连接池 + 参数化查询)                                        │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 关键数据流

```
问答请求
    │
    ▼
SessionService.create_new_session()
    │
    ├─→ SessionRepository.create_session()
    │
    ▼
SessionService.add_message(user)
    │
    ├─→ MessageRepository.add_message()
    │
    ▼
Knowledge Agent Graph (检索→生成→质量评估)
    │
    ├─→ RetrievalLogService.log_retrieval_start()
    │   └─→ RetrievalLogRepository.create_retrieval_log()
    │
    ├─→ RetrievalLogService.log_retrieval_results()
    │   └─→ RetrievalLogRepository.add_retrieval_result()
    │
    ├─→ QualityLogService.log_quality_assessment()
    │   └─→ QualityLogRepository.insert_quality_log()
    │
    ▼
SessionService.add_message(assistant)
    │
    ├─→ MessageRepository.add_message()
    │
    ▼
MemoryService.extract_short_term_memory()
    │
    ├─→ LLM (提取记忆内容)
    │
    ├─→ MemoryService.save_short_term_memory()
    │   └─→ MemoryRepository.insert_short_term_memory()
    │
    └─→ MemoryService.trigger_long_term_memory()
        └─→ MemoryRepository.insert_long_term_memory() (如果触发)
```

---

## 5. 定时任务函数

| 函数名 | 执行频率 | 功能说明 |
|--------|---------|---------|
| `MemoryService.cleanup_expired_memories()` | 每天凌晨 2 点 | 清理过期短期记忆 |
| `MemoryService.merge_similar_memories()` | 每周日凌晨 3 点 | 合并相似长期记忆 |
| `QualityLogService.archive_old_logs()` | 每月 1 号凌晨 4 点 | 归档 90 天前的质量日志 |
| `RetrievalLogService.archive_old_logs()` | 每月 1 号凌晨 5 点 | 归档 90 天前的检索日志 |

---

## 6. 函数参数类型定义

### 6.1 通用类型别名

```python
# 唯一标识符
SessionUUID = bytes  # BINARY(16)
MessageUUID = bytes  # BINARY(16)
MemoryID = int
QualityID = int
RetrievalID = int

# 评分类型
Score = float  # 0.0 - 1.0
Rating = int   # 1-5 星

# 时间类型
Timestamp = str  # ISO format: "2026-04-28T12:00:00"

# JSON 类型
Entities = Dict[str, List[str]]  # {"person": ["张三"], "org": ["公司 A"]}
KeyFacts = Dict[str, str]  # {"主题": "事实描述"}
Tags = List[str]  # ["工作", "学习", "重要"]
Issues = List[Dict]  # [{"issue_type": "hallucination", "severity": "high", "description": "..."}]
```

---

## 总结

本文档定义了持久化层的完整函数接口：

1. **Repository 层**: 6 个 Repository，共约 50+ 个函数
2. **Service 层**: 5 个 Service，共约 40+ 个函数
3. **工作链路**: 完整展示了从用户提问到答案返回的函数调用流程
4. **定时任务**: 3 个定时清理/归档任务

所有函数遵循**分层解耦**原则，Service 层调用 Repository 层，Repository 层调用 MySQL Client，便于测试和维护。
