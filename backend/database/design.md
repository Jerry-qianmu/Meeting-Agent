# Knowledge Agent 持久化设计文档

> **版本**: v1.0  
> **最后更新**: 2026-04-28  
> **作者**: Hermes Agent

---

## 目录

1. [设计原则](#1-设计原则)
2. [架构总览](#2-架构总览)
3. [数据库选型与职责](#3-数据库选型与职责)
4. [表结构设计](#4-表结构设计)
5. [记忆系统设计](#5-记忆系统设计)
6. [检索日志与可追溯性](#6-检索日志与可追溯性)
7. [质量评估数据持久化](#7-质量评估数据持久化)
8. [Repository 层设计](#8-repository-层设计)
9. [性能优化建议](#9-性能优化建议)
10. [附录：SQL DDL](#10-附录 sql-ddl)

---

## 1. 设计原则

### 1.1 核心原则

| 原则 | 说明 |
|------|------|
| **读写分离** | MySQL 存元数据/日志，Milvus 存向量/检索 |
| **分层解耦** | API → Service → Repository → DB |
| **可扩展性** | 新表不影响旧逻辑，字段可增量添加 |
| **可追溯性** | 每次检索、每次问答都有完整日志 |
| **性能优先** | 高增长表（retrieval_log）按月分区 |

### 1.2 不修改现有代码

- 本文档仅**新增**表和 Repository，**不修改**现有 `database_schema.py` 中的表结构
- 所有新增表通过新 DDL 文件管理，避免冲突

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                     Knowledge Agent Graph                        │
│  query_rewrite → retrieve → rerank → generate → quality_check   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Service 层                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │SessionService│  │MemoryService │  │RetrievalLogService   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Repository 层                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │SessionRepo   │  │MemoryRepo    │  │RetrievalLogRepo      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼                               ▼
┌─────────────────────────┐    ┌─────────────────────────────────┐
│       MySQL             │    │           Milvus                │
│  - Session/Message      │    │  - 向量检索                      │
│  - 记忆/反馈/日志        │    │  - Dense + BM25                 │
└─────────────────────────┘    └─────────────────────────────────┘
```

---

## 3. 数据库选型与职责

| 数据库 | 职责 | 数据类型 | 增长特点 |
|--------|------|---------|---------|
| **MySQL** | 业务元数据、会话、记忆、日志、反馈 | 结构化文本/数字 | 中高速增长 |
| **Milvus** | 向量检索、知识切片 | 向量 + 文本 | 高增长（每个文档多次切片） |

### 3.1 MySQL 表分类

| 分类 | 表名 | 说明 |
|------|------|------|
| **核心业务** | `session`, `message` | 会话与消息（已有） |
| **记忆系统** | `short_term_memory`, `long_term_memory` | 短期/长期记忆（新增） |
| **检索日志** | `retrieval_log`, `retrieval_result` | 检索过程记录（已有，需增强） |
| **质量评估** | `quality_log`, `answer_feedback` | 质量评估结果（新增） |
| **知识库** | `kb`, `document`, `chunk` | 知识库结构（已有） |

---

## 4. 表结构设计

### 4.1 记忆系统表（新增）

#### 4.1.1 短期记忆表 `short_term_memory`

**用途**：存储最近 N 轮对话的关键信息，用于上下文指代消解

```sql
CREATE TABLE IF NOT EXISTS short_term_memory (
    memory_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_uuid BINARY(16) NOT NULL COMMENT '会话 ID',
    user_id BINARY(16) NOT NULL COMMENT '用户 ID',
    
    -- 记忆内容
    query_summary VARCHAR(500) COMMENT '用户问题摘要',
    answer_summary VARCHAR(1000) COMMENT '答案摘要',
    entities JSON COMMENT '提取的实体（人名、组织、时间等）',
    key_facts JSON COMMENT '关键事实（key-value 对）',
    
    -- 元数据
    message_uuid BINARY(16) COMMENT '关联的消息 ID',
    relevance_score FLOAT DEFAULT 1.0 COMMENT '与当前会话的相关性',
    access_count INT DEFAULT 1 COMMENT '被引用次数',
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 过期控制
    expires_at TIMESTAMP NULL COMMENT '过期时间（NULL=永久）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_session (session_uuid),
    INDEX idx_user (user_id),
    INDEX idx_expires (expires_at),
    INDEX idx_last_accessed (last_accessed_at)
) ENGINE=InnoDB COMMENT='短期记忆表（最近 N 轮对话）';
```

#### 4.1.2 长期记忆表 `long_term_memory`

**用途**：跨会话的用户偏好、习惯、重要事实

```sql
CREATE TABLE IF NOT EXISTS long_term_memory (
    memory_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BINARY(16) NOT NULL COMMENT '用户 ID',
    
    -- 记忆类型
    memory_type VARCHAR(50) NOT NULL COMMENT 'preference/habit/fact/relationship',
    category VARCHAR(100) COMMENT '分类（如：工作偏好、学习主题等）',
    
    -- 记忆内容
    title VARCHAR(255) COMMENT '记忆标题',
    content TEXT NOT NULL COMMENT '记忆内容',
    tags JSON COMMENT '标签（用于检索）',
    
    -- 权重与评分
    importance_score FLOAT DEFAULT 0.5 COMMENT '重要性（0-1）',
    confidence_score FLOAT DEFAULT 0.8 COMMENT '置信度（0-1）',
    access_count INT DEFAULT 0 COMMENT '被引用次数',
    
    -- 来源追溯
    source_type VARCHAR(50) COMMENT 'source: session/feedback/manual',
    source_uuid BINARY(16) COMMENT '来源会话/消息 ID',
    
    -- 元数据
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP NULL,
    
    -- 索引
    INDEX idx_user (user_id),
    INDEX idx_type (memory_type),
    INDEX idx_active (is_active),
    INDEX idx_importance (importance_score DESC)
) ENGINE=InnoDB COMMENT='长期记忆表（用户偏好/习惯/重要事实）';
```

### 4.2 质量评估表（新增）

#### 4.2.1 质量评估日志表 `quality_log`

**用途**：记录每次问答的质量评估结果，用于优化和调试

```sql
CREATE TABLE IF NOT EXISTS quality_log (
    quality_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_uuid BINARY(16) NOT NULL,
    message_uuid BINARY(16) NOT NULL,
    
    -- 检索信息
    query TEXT NOT NULL COMMENT '用户问题',
    rewritten_query TEXT COMMENT '改写后的问题',
    retrieval_strategy VARCHAR(50) COMMENT '检索策略：vector/keyword/hybrid',
    chunks_retrieved INT DEFAULT 0 COMMENT '检索到的 chunk 数量',
    
    -- 生成信息
    answer TEXT NOT NULL COMMENT '生成的答案',
    answer_length INT COMMENT '答案长度（字符数）',
    context_tokens INT COMMENT '使用的上下文 token 数',
    
    -- 质量评分
    quality_score FLOAT COMMENT '总分（0-1）',
    relevance_score FLOAT COMMENT '相关性（0-1）',
    groundedness_score FLOAT COMMENT 'groundedness（0-1）',
    completeness_score FLOAT COMMENT '完整性（0-1）',
    factuality_score FLOAT COMMENT '事实性（0-1）',
    
    -- 评估结果
    quality_passed BOOLEAN COMMENT '是否通过质量检查',
    should_retry BOOLEAN COMMENT '是否触发重试',
    retry_count INT DEFAULT 0 COMMENT '实际重试次数',
    fallback_used BOOLEAN COMMENT '是否使用了 fallback',
    
    -- 问题诊断
    issues JSON COMMENT '检测到的问题列表',
    
    -- 耗时统计
    total_duration_ms INT COMMENT '总耗时（毫秒）',
    retrieval_duration_ms INT COMMENT '检索耗时',
    generation_duration_ms INT COMMENT '生成耗时',
    quality_check_duration_ms INT COMMENT '质量评估耗时',
    
    -- 元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_session (session_uuid),
    INDEX idx_message (message_uuid),
    INDEX idx_quality_score (quality_score),
    INDEX idx_passed (quality_passed),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB COMMENT='质量评估日志表';
```

#### 4.2.2 用户反馈表 `answer_feedback`（增强已有 `feedback`）

**用途**：收集用户对答案的显式反馈

```sql
-- 原 feedback 表增强（新增字段）
ALTER TABLE IF EXISTS feedback ADD COLUMN IF NOT EXISTS feedback_type VARCHAR(50) DEFAULT 'rating' COMMENT 'rating/text/mixed';
ALTER TABLE IF EXISTS feedback ADD COLUMN IF NOT EXISTS quality_refused BOOLEAN DEFAULT FALSE COMMENT '是否因质量拒绝';
ALTER TABLE IF EXISTS feedback ADD COLUMN IF NOT EXISTS helpful BOOLEAN COMMENT '是否有帮助';
ALTER TABLE IF EXISTS feedback ADD COLUMN IF NOT EXISTS feedback_details JSON COMMENT '详细反馈内容';
```

### 4.3 检索日志增强（已有表优化）

#### 4.3.1 检索日志表 `retrieval_log`（已有，需增强）

```sql
-- 新增字段
ALTER TABLE IF EXISTS retrieval_log ADD COLUMN IF NOT EXISTS query_rewrite TEXT COMMENT '改写后的查询';
ALTER TABLE IF EXISTS retrieval_log ADD COLUMN IF NOT EXISTS retrieval_strategy VARCHAR(50) COMMENT '检索策略';
ALTER TABLE IF EXISTS retrieval_log ADD COLUMN IF NOT EXISTS chunks_before_filter INT COMMENT '过滤前 chunk 数';
ALTER TABLE IF EXISTS retrieval_log ADD COLUMN IF NOT EXISTS chunks_after_filter INT COMMENT '过滤后 chunk 数';
ALTER TABLE IF EXISTS retrieval_log ADD COLUMN IF NOT EXISTS rerank_used BOOLEAN DEFAULT FALSE;
ALTER TABLE IF EXISTS retrieval_log ADD COLUMN IF NOT EXISTS quality_triggered BOOLEAN DEFAULT FALSE COMMENT '是否触发质量重试';
ALTER TABLE IF EXISTS retrieval_log ADD COLUMN IF NOT EXISTS final_answer_length INT COMMENT '最终答案长度';
```

#### 4.3.2 检索结果表 `retrieval_result`（已有）

保持不变，用于记录每次检索的具体 chunk 和分数。

---

## 5. 记忆系统设计

### 5.1 记忆分类

```
┌─────────────────────────────────────────────────────────────┐
│                      记忆系统                                │
├──────────────────────┬──────────────────────────────────────┤
│    短期记忆          │          长期记忆                    │
├──────────────────────┼──────────────────────────────────────┤
│ - 最近 N 轮对话       │ - 用户偏好（preference）             │
│ - 指代消解上下文     │ - 行为习惯（habit）                  │
│ - 临时关键事实       │ - 重要事实（fact）                   │
│                      │ - 关系网络（relationship）           │
├──────────────────────┼──────────────────────────────────────┤
│ 存储：MySQL          │ 存储：MySQL                          │
│ 周期：会话期间 + N 天 │ 周期：永久（可设置过期）              │
│ 容量：每会话 ~100 条  │ 容量：每用户 ~1000 条                 │
└──────────────────────┴──────────────────────────────────────┘
```

### 5.2 记忆提取与更新策略

#### 5.2.1 短期记忆提取

```python
# 在 query_rewrite 节点中调用
def extract_short_term_memory(session_uuid: str, query: str, answer: str):
    """
    从对话中提取短期记忆
    
    提取内容：
    1. 问题摘要（去指代化）
    2. 答案摘要（关键信息）
    3. 命名实体（人名、组织、时间）
    4. 关键事实（key-value 对）
    """
    # 调用 LLM 提取
    memory = llm_extract_memory(query, answer)
    
    # 写入数据库
    short_term_repo.insert({
        "session_uuid": session_uuid,
        "query_summary": memory["query_summary"],
        "answer_summary": memory["answer_summary"],
        "entities": memory["entities"],
        "key_facts": memory["key_facts"],
        "message_uuid": current_message_uuid
    })
```

#### 5.2.2 长期记忆触发条件

| 触发条件 | 记忆类型 | 操作 |
|---------|---------|------|
| 用户明确表达偏好 | `preference` | 创建/更新 |
| 同一主题多次询问 | `fact` | 更新重要性分数 |
| 用户标记「重要」 | `fact` | 提升重要性 + 永久保存 |
| 负面反馈（质量差） | `preference` | 记录不喜欢的主题/方式 |

#### 5.2.3 记忆检索

```python
def retrieve_memories(user_id: str, query: str, memory_type: str = "all", top_k: int = 5):
    """
    检索相关记忆
    
    Args:
        user_id: 用户 ID
        query: 当前查询
        memory_type: short/long/all
        top_k: 返回数量
    
    Returns:
        List[Memory] 按相关性排序的记忆列表
    """
    # 1. 短期记忆：按时间倒序
    if memory_type in ["short", "all"]:
        short_mems = short_term_repo.get_recent(session_uuid, limit=10)
    
    # 2. 长期记忆：按相关性和重要性
    if memory_type in ["long", "all"]:
        long_mems = long_term_repo.search_by_relevance(
            user_id=user_id,
            query=query,
            top_k=top_k
        )
    
    # 3. 合并排序
    return merge_and_rerank(short_mems, long_mems)
```

---

## 6. 检索日志与可追溯性

### 6.1 完整链路追踪

```
query_rewrite
    │
    ├─ processing_log → retrieval_log (query_rewrite 阶段)
    │
    ▼
retrieval (doc_retrieval)
    │
    ├─ retrieval_log (检索参数、chunk 数量)
    ├─ retrieval_result (每个 chunk 的分数)
    │
    ▼
rerank
    │
    ├─ retrieval_result (更新 rerank_score)
    │
    ▼
generate_answer
    │
    ├─ retrieval_log (context_tokens, answer_length)
    │
    ▼
quality_control
    │
    ├─ quality_log (所有质量评分)
    │
    ▼
retrieval_retry (如果触发)
    │
    └─ retrieval_log (更新 retry_count, final_answer_length)
```

### 6.2 日志记录时机

| 节点 | 记录内容 | 写入表 |
|------|---------|-------|
| `query_rewrite` | 原问题、改写后问题 | `retrieval_log` |
| `doc_retrieval` | 检索策略、top_k、filter | `retrieval_log`, `retrieval_result` |
| `light_filter` | 过滤前后数量 | `retrieval_log` |
| `rerank` | 是否使用 rerank、rerank 模型 | `retrieval_log` |
| `generate_answer` | context_tokens、answer_length | `retrieval_log` |
| `quality_control` | 所有质量评分、是否重试 | `quality_log` |
| `feedback` | 用户评分、评论 | `feedback` / `answer_feedback` |

---

## 7. 质量评估数据持久化

### 7.1 质量评估流程

```
generate_answer
    │
    ▼
quality_control (规则评估 + LLM 评估)
    │
    ├─ quality_score (总分)
    ├─ breakdown (relevance/groundedness/completeness/factuality)
    ├─ issues (问题列表)
    │
    ▼
quality_log (持久化)
    │
    ├─ 如果 passed=True → 返回答案
    └─ 如果 passed=False → 触发重试 → 记录 retry_count
```

### 7.2 质量数据分析

利用 `quality_log` 表可以进行以下分析：

| 分析目标 | SQL 示例 |
|---------|---------|
| 总体通过率 | `SELECT AVG(quality_passed) FROM quality_log` |
| 各维度平均分 | `SELECT AVG(relevance_score), AVG(groundedness_score)...` |
| 重试率 | `SELECT AVG(should_retry) FROM quality_log` |
| 常见问题类型 | `SELECT issues->>'$.issue_type', COUNT(*) FROM quality_log GROUP BY 1` |
| 检索策略对比 | `SELECT retrieval_strategy, AVG(quality_score) FROM quality_log GROUP BY 1` |

---

## 8. Repository 层设计

### 8.1 目录结构

```
backend/database/mysql/repository/
├── BaseRepository.py          # 已有
├── session_repository.py      # 会话管理
├── memory_repository.py       # 记忆系统（新增）
├── retrieval_log_repository.py # 检索日志（新增）
├── quality_log_repository.py  # 质量日志（新增）
└── feedback_repository.py     # 反馈管理（新增）
```

### 8.2 Repository 示例

#### 8.2.1 MemoryRepository

```python
# backend/database/mysql/repository/memory_repository.py

from typing import List, Dict, Any, Optional
from BaseRepository import BaseRepository

class MemoryRepository(BaseRepository):
    """记忆系统 Repository"""
    
    # ── 短期记忆 ──────────────────────────────────────────────────
    
    def insert_short_term(self, data: Dict[str, Any]) -> int:
        """插入短期记忆"""
        sql = """
            INSERT INTO short_term_memory 
            (session_uuid, user_id, query_summary, answer_summary, 
             entities, key_facts, message_uuid, created_at)
            VALUES (%(session_uuid)s, %(user_id)s, %(query_summary)s, 
                    %(answer_summary)s, %(entities)s, %(key_facts)s, 
                    %(message_uuid)s, NOW())
        """
        return self.execute(sql, data)
    
    def get_recent(self, session_uuid: str, limit: int = 10) -> List[Dict]:
        """获取最近 N 条短期记忆"""
        sql = """
            SELECT * FROM short_term_memory
            WHERE session_uuid = %(session_uuid)s
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """
        return self.fetch_all(sql, {"session_uuid": session_uuid, "limit": limit})
    
    def cleanup_expired(self) -> int:
        """清理过期记忆"""
        sql = """
            DELETE FROM short_term_memory
            WHERE expires_at IS NOT NULL AND expires_at <= NOW()
        """
        return self.execute(sql)
    
    # ── 长期记忆 ──────────────────────────────────────────────────
    
    def insert_long_term(self, data: Dict[str, Any]) -> int:
        """插入长期记忆"""
        sql = """
            INSERT INTO long_term_memory 
            (user_id, memory_type, category, title, content, 
             tags, importance_score, source_type, source_uuid)
            VALUES (%(user_id)s, %(memory_type)s, %(category)s, 
                    %(title)s, %(content)s, %(tags)s, 
                    %(importance_score)s, %(source_type)s, %(source_uuid)s)
        """
        return self.execute(sql, data)
    
    def search_by_relevance(
        self, 
        user_id: str, 
        query: str, 
        top_k: int = 5
    ) -> List[Dict]:
        """基于相关性和重要性检索长期记忆"""
        sql = """
            SELECT * FROM long_term_memory
            WHERE user_id = %(user_id)s
              AND is_active = TRUE
            ORDER BY 
                importance_score DESC,
                access_count DESC,
                created_at DESC
            LIMIT %(top_k)s
        """
        return self.fetch_all(sql, {"user_id": user_id, "top_k": top_k})
    
    def update_access_count(self, memory_id: int) -> int:
        """更新记忆访问次数"""
        sql = """
            UPDATE long_term_memory
            SET access_count = access_count + 1,
                last_accessed_at = NOW()
            WHERE memory_id = %(memory_id)s
        """
        return self.execute(sql, {"memory_id": memory_id})
```

#### 8.2.2 QualityLogRepository

```python
# backend/database/mysql/repository/quality_log_repository.py

from typing import List, Dict, Any, Optional
from BaseRepository import BaseRepository

class QualityLogRepository(BaseRepository):
    """质量评估日志 Repository"""
    
    def insert(self, data: Dict[str, Any]) -> int:
        """插入质量评估记录"""
        sql = """
            INSERT INTO quality_log 
            (session_uuid, message_uuid, query, rewritten_query, 
             retrieval_strategy, chunks_retrieved, answer, answer_length,
             context_tokens, quality_score, relevance_score, 
             groundedness_score, completeness_score, factuality_score,
             quality_passed, should_retry, retry_count, fallback_used,
             issues, total_duration_ms, retrieval_duration_ms,
             generation_duration_ms, quality_check_duration_ms)
            VALUES (%(session_uuid)s, %(message_uuid)s, %(query)s, 
                    %(rewritten_query)s, %(retrieval_strategy)s, 
                    %(chunks_retrieved)s, %(answer)s, %(answer_length)s,
                    %(context_tokens)s, %(quality_score)s, 
                    %(relevance_score)s, %(groundedness_score)s,
                    %(completeness_score)s, %(factuality_score)s,
                    %(quality_passed)s, %(should_retry)s, %(retry_count)s,
                    %(fallback_used)s, %(issues)s, %(total_duration_ms)s,
                    %(retrieval_duration_ms)s, %(generation_duration_ms)s,
                    %(quality_check_duration_ms)s)
        """
        return self.execute(sql, data)
    
    def get_statistics(
        self, 
        start_date: str = None, 
        end_date: str = None
    ) -> Dict[str, Any]:
        """获取质量统计数据"""
        params = {}
        date_filter = ""
        if start_date:
            date_filter += " AND created_at >= %(start_date)s"
            params["start_date"] = start_date
        if end_date:
            date_filter += " AND created_at <= %(end_date)s"
            params["end_date"] = end_date
        
        sql = f"""
            SELECT 
                COUNT(*) as total_count,
                AVG(quality_score) as avg_quality_score,
                AVG(relevance_score) as avg_relevance,
                AVG(groundedness_score) as avg_groundedness,
                AVG(completeness_score) as avg_completeness,
                AVG(factuality_score) as avg_factuality,
                AVG(CASE WHEN quality_passed THEN 1 ELSE 0 END) as pass_rate,
                AVG(CASE WHEN should_retry THEN 1 ELSE 0 END) as retry_rate,
                AVG(retry_count) as avg_retry_count,
                AVG(CASE WHEN fallback_used THEN 1 ELSE 0 END) as fallback_rate
            FROM quality_log
            WHERE 1=1 {date_filter}
        """
        return self.fetch_one(sql, params)
    
    def get_failed_queries(
        self, 
        limit: int = 100
    ) -> List[Dict]:
        """获取质量未通过的查询，用于分析"""
        sql = """
            SELECT query, issues, quality_score, created_at
            FROM quality_log
            WHERE quality_passed = FALSE
            ORDER BY created_at DESC
            LIMIT %(limit)s
        """
        return self.fetch_all(sql, {"limit": limit})
```

---

## 9. 性能优化建议

### 9.1 索引优化

| 表 | 索引建议 | 说明 |
|----|---------|------|
| `short_term_memory` | `(session_uuid, created_at DESC)` | 按会话和时间查询 |
| `long_term_memory` | `(user_id, memory_type, is_active)` | 按用户和类型过滤 |
| `quality_log` | `(created_at DESC)` | 按时间查询统计 |
| `retrieval_log` | `(session_uuid, created_at)` | 会话检索历史 |

### 9.2 分区策略

```sql
-- retrieval_log 按月分区（高增长表）
ALTER TABLE retrieval_log 
PARTITION BY RANGE (YEAR(created_at) * 100 + MONTH(created_at)) (
    PARTITION p202601 VALUES LESS THAN (202602),
    PARTITION p202602 VALUES LESS THAN (202603),
    ...
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

### 9.3 数据归档

```python
# 定时任务：归档 3 个月前的质量日志
def archive_old_quality_logs(days: int = 90):
    """
    将旧数据归档到 history 表
    """
    # 1. 复制到归档表
    # INSERT INTO quality_log_archive SELECT * FROM quality_log WHERE created_at < NOW() - INTERVAL 90 DAY
    
    # 2. 删除原表数据
    # DELETE FROM quality_log WHERE created_at < NOW() - INTERVAL 90 DAY
```

### 9.4 缓存策略

| 数据 | 缓存方式 | TTL |
|------|---------|-----|
| 短期记忆 | Redis | 会话期间 + 24 小时 |
| 长期记忆 | Redis | 7 天 |
| 质量统计 | Redis | 1 小时 |

---

## 10. 附录：SQL DDL

### 10.1 记忆系统表 DDL

```sql
-- 短期记忆表
CREATE TABLE IF NOT EXISTS short_term_memory (
    memory_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_uuid BINARY(16) NOT NULL,
    user_id BINARY(16) NOT NULL,
    query_summary VARCHAR(500),
    answer_summary VARCHAR(1000),
    entities JSON,
    key_facts JSON,
    message_uuid BINARY(16),
    relevance_score FLOAT DEFAULT 1.0,
    access_count INT DEFAULT 1,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_uuid),
    INDEX idx_user (user_id),
    INDEX idx_expires (expires_at),
    INDEX idx_last_accessed (last_accessed_at)
) ENGINE=InnoDB COMMENT='短期记忆表';

-- 长期记忆表
CREATE TABLE IF NOT EXISTS long_term_memory (
    memory_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BINARY(16) NOT NULL,
    memory_type VARCHAR(50) NOT NULL,
    category VARCHAR(100),
    title VARCHAR(255),
    content TEXT NOT NULL,
    tags JSON,
    importance_score FLOAT DEFAULT 0.5,
    confidence_score FLOAT DEFAULT 0.8,
    access_count INT DEFAULT 0,
    source_type VARCHAR(50),
    source_uuid BINARY(16),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP NULL,
    INDEX idx_user (user_id),
    INDEX idx_type (memory_type),
    INDEX idx_active (is_active),
    INDEX idx_importance (importance_score DESC)
) ENGINE=InnoDB COMMENT='长期记忆表';
```

### 10.2 质量评估表 DDL

```sql
-- 质量评估日志表
CREATE TABLE IF NOT EXISTS quality_log (
    quality_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_uuid BINARY(16) NOT NULL,
    message_uuid BINARY(16) NOT NULL,
    query TEXT NOT NULL,
    rewritten_query TEXT,
    retrieval_strategy VARCHAR(50),
    chunks_retrieved INT DEFAULT 0,
    answer TEXT NOT NULL,
    answer_length INT,
    context_tokens INT,
    quality_score FLOAT,
    relevance_score FLOAT,
    groundedness_score FLOAT,
    completeness_score FLOAT,
    factuality_score FLOAT,
    quality_passed BOOLEAN,
    should_retry BOOLEAN,
    retry_count INT DEFAULT 0,
    fallback_used BOOLEAN,
    issues JSON,
    total_duration_ms INT,
    retrieval_duration_ms INT,
    generation_duration_ms INT,
    quality_check_duration_ms INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_uuid),
    INDEX idx_message (message_uuid),
    INDEX idx_quality_score (quality_score),
    INDEX idx_passed (quality_passed),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB COMMENT='质量评估日志表';
```

---

## 总结

本文档提供了 Knowledge Agent 的完整持久化设计方案：

1. **记忆系统**：短期记忆（会话上下文）+ 长期记忆（用户偏好/习惯）
2. **质量评估**：完整记录每次问答的质量评分和诊断信息
3. **检索日志**：增强现有表，支持完整的链路追踪
4. **Repository 层**：分层解耦，便于测试和维护
5. **性能优化**：索引、分区、缓存策略

所有设计遵循**不修改现有代码**原则，通过新增表和 Repository 实现功能扩展。
