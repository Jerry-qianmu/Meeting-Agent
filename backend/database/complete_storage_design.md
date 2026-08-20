# Knowledge Agent 完整持久化与存储设计文档

> **版本**: v2.0  
> **最后更新**: 2026-04-28  
> **说明**: 包含 MySQL 表结构、OSS 存储、文档/知识库存储的完整设计

---

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [MySQL 数据库设计](#2-mysql-数据库设计)
3. [OSS 对象存储设计](#3-oss-对象存储设计)
4. [Milvus 向量数据库设计](#4-milvus-向量数据库设计)
5. [文档处理流程存储设计](#5-文档处理流程存储设计)
6. [知识库管理存储设计](#6-知识库管理存储设计)
7. [跨存储系统关系图](#7-跨存储系统关系图)

---

## 1. 系统架构总览

### 1.1 存储系统分工

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Knowledge Agent 系统                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│      MySQL          │  │       OSS           │  │      Milvus         │
│  (结构化数据)        │  │  (文件存储)          │  │  (向量检索)          │
├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
│ - 用户/会话/消息     │  │ - 原始文档 (PDF/Word) │  │ - 文本向量 (dense)   │
│ - 记忆系统          │  │ - 处理中间文件       │  │ - BM25 稀疏向量      │
│ - 日志/反馈         │  │ - 缩略图/预览        │  │ - 元数据过滤字段    │
│ - 知识库元数据      │  │ - 导出报告          │  │ - 分组字段          │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
```

### 1.2 存储系统选型

| 存储系统 | 用途 | 数据特点 | 增长预估 |
|---------|------|---------|---------|
| **MySQL** | 业务元数据、日志、记忆 | 结构化，关系型 | 中等增长 (~GB/年) |
| **OSS** | 文件存储 | 非结构化，大文件 | 高速增长 (~TB/年) |
| **Milvus** | 向量检索 | 向量 + 文本 | 高速增长 (~亿级向量) |

---

## 2. MySQL 数据库设计

### 2.1 用户与认证表

#### 2.1.1 user（用户表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| user_id | BINARY | 16 | NO | - | 用户唯一 ID（UUID 转二进制） |
| username | VARCHAR | 100 | NO | - | 用户名（唯一） |
| email | VARCHAR | 255 | YES | NULL | 邮箱 |
| password_hash | VARCHAR | 255 | NO | - | 密码哈希 |
| avatar_url | VARCHAR | 500 | YES | NULL | 头像 OSS 路径 |
| status | TINYINT | 1 | NO | 1 | 状态：0=禁用，1=启用 |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 更新时间 |
| last_login_at | TIMESTAMP | - | YES | NULL | 最后登录时间 |

**索引**:
- `PRIMARY KEY (user_id)`
- `UNIQUE KEY uk_username (username)`
- `UNIQUE KEY uk_email (email)`
- `INDEX idx_status (status)`

---

### 2.2 会话与消息表

#### 2.2.1 session（会话表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| session_uuid | BINARY | 16 | NO | - | 会话唯一 ID |
| user_id | BINARY | 16 | NO | - | 用户 ID |
| title | VARCHAR | 255 | YES | NULL | 会话标题 |
| summary | TEXT | - | YES | NULL | 会话摘要（LLM 生成） |
| status | TINYINT | 1 | NO | 1 | 状态：0=归档，1=进行中 |
| message_count | INT | - | NO | 0 | 消息数量（冗余，提升查询性能） |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 更新时间 |

**索引**:
- `PRIMARY KEY (session_uuid)`
- `INDEX idx_user (user_id)`
- `INDEX idx_user_status (user_id, status)`
- `INDEX idx_updated_at (updated_at DESC)`

**设计说明**:
- session 表**不存储** knowledge_base_ids 或 document_ids
- 知识库/文档选择在前端进行，检索时作为 filter 条件传递给 Milvus
- 这种设计支持同一个会话中动态切换知识库/文档

#### 2.2.2 message（消息表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| message_uuid | BINARY | 16 | NO | - | 消息唯一 ID |
| session_uuid | BINARY | 16 | NO | - | 会话 ID |
| user_id | BINARY | 16 | NO | - | 用户 ID（冗余，便于查询） |
| role | TINYINT | 1 | NO | - | 0=user, 1=assistant, 2=system |
| content | MEDIUMTEXT | - | NO | - | 消息内容 |
| parent_message_id | BINARY | 16 | YES | NULL | 父消息 ID（支持多轮追问） |
| model_used | VARCHAR | 100 | YES | NULL | 使用的模型 |
| tokens_used | INT | - | YES | NULL | 消耗的 token 数 |
| latency_ms | INT | - | YES | NULL | 响应耗时 |
| status | TINYINT | 1 | NO | 1 | 0=草稿，1=完成，2=失败 |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |

**索引**:
- `PRIMARY KEY (message_uuid)`
- `INDEX idx_session (session_uuid, created_at)`
- `INDEX idx_user (user_id, created_at)`
- `INDEX idx_role (role)`

---

### 2.3 记忆系统表

#### 2.3.1 short_term_memory（短期记忆表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| memory_id | BIGINT | - | NO | AUTO_INCREMENT | 记忆 ID |
| session_uuid | BINARY | 16 | NO | - | 会话 ID |
| user_id | BINARY | 16 | NO | - | 用户 ID |
| query_summary | VARCHAR | 500 | YES | NULL | 问题摘要 |
| answer_summary | VARCHAR | 1000 | YES | NULL | 答案摘要 |
| entities | JSON | - | YES | NULL | 提取的实体 {"person": [], "org": []} |
| key_facts | JSON | - | YES | NULL | 关键事实 {"key": "value"} |
| message_uuid | BINARY | 16 | YES | NULL | 关联的消息 ID |
| relevance_score | FLOAT | - | NO | 1.0 | 相关性分数 |
| access_count | INT | - | NO | 1 | 访问次数 |
| last_accessed_at | TIMESTAMP | - | YES | CURRENT_TIMESTAMP | 最后访问时间 |
| expires_at | TIMESTAMP | - | YES | NULL | 过期时间（NULL=永久） |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |

**索引**:
- `PRIMARY KEY (memory_id)`
- `INDEX idx_session (session_uuid, created_at DESC)`
- `INDEX idx_user (user_id)`
- `INDEX idx_expires (expires_at)`
- `INDEX idx_last_accessed (last_accessed_at)`

#### 2.3.2 long_term_memory（长期记忆表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| memory_id | BIGINT | - | NO | AUTO_INCREMENT | 记忆 ID |
| user_id | BINARY | 16 | NO | - | 用户 ID |
| memory_type | VARCHAR | 50 | NO | - | preference/habit/fact/relationship |
| category | VARCHAR | 100 | YES | NULL | 分类（如：工作偏好、学习主题） |
| title | VARCHAR | 255 | YES | NULL | 记忆标题 |
| content | TEXT | - | NO | - | 记忆内容 |
| tags | JSON | - | YES | NULL | 标签 ["工作", "重要"] |
| importance_score | FLOAT | - | NO | 0.5 | 重要性（0-1） |
| confidence_score | FLOAT | - | NO | 0.8 | 置信度（0-1） |
| access_count | INT | - | NO | 0 | 访问次数 |
| source_type | VARCHAR | 50 | YES | NULL | source/session/feedback/manual |
| source_uuid | BINARY | 16 | YES | NULL | 来源会话/消息 ID |
| is_active | BOOLEAN | - | NO | TRUE | 是否启用 |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 更新时间 |
| last_accessed_at | TIMESTAMP | - | YES | NULL | 最后访问时间 |

**索引**:
- `PRIMARY KEY (memory_id)`
- `INDEX idx_user (user_id, is_active)`
- `INDEX idx_type (memory_type)`
- `INDEX idx_category (category)`
- `INDEX idx_importance (importance_score DESC)`
- `INDEX idx_active (is_active)`

---

### 2.4 知识库与文档表

#### 2.4.1 knowledge_base（知识库表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| kb_uuid | BINARY | 16 | NO | - | 知识库唯一 ID |
| user_id | BINARY | 16 | NO | - | 所有者用户 ID |
| name | VARCHAR | 255 | NO | - | 知识库名称 |
| description | TEXT | - | YES | NULL | 描述 |
| collection_name | VARCHAR | 100 | YES | NULL | Milvus collection 名称 |
| doc_count | INT | - | NO | 0 | 文档数量（冗余） |
| chunk_count | INT | - | NO | 0 | 切片数量（冗余） |
| total_tokens | BIGINT | - | NO | 0 | 总 token 数 |
| status | TINYINT | 1 | NO | 1 | 0=创建中，1=可用，2=处理中，3=禁用 |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 更新时间 |

**索引**:
- `PRIMARY KEY (kb_uuid)`
- `INDEX idx_user (user_id)`
- `INDEX idx_status (status)`
- `INDEX idx_collection (collection_name)`

#### 2.4.2 document（文档表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| doc_uuid | BINARY | 16 | NO | - | 文档唯一 ID |
| kb_uuid | BINARY | 16 | NO | - | 知识库 ID |
| user_id | BINARY | 16 | NO | - | 上传用户 ID |
| title | VARCHAR | 255 | YES | NULL | 文档标题 |
| original_filename | VARCHAR | 500 | NO | - | 原始文件名 |
| file_size | BIGINT | - | NO | - | 文件大小（字节） |
| file_type | VARCHAR | 50 | NO | - | PDF/DOCX/TXT/MD 等 |
| oss_path | VARCHAR | 1000 | NO | - | OSS 存储路径 |
| oss_bucket | VARCHAR | 100 | YES | NULL | OSS 存储桶名称 |
| chunk_count | INT | - | NO | 0 | 切片数量 |
| total_tokens | BIGINT | - | NO | 0 | 总 token 数 |
| status | TINYINT | 1 | NO | 0 | 0=pending, 1=processing, 2=done, 3=failed |
| processing_error | TEXT | - | YES | NULL | 处理错误信息 |
| version | INT | - | NO | 1 | 版本号（支持文档更新） |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 更新时间 |

**索引**:
- `PRIMARY KEY (doc_uuid)`
- `INDEX idx_kb (kb_uuid)`
- `INDEX idx_user (user_id)`
- `INDEX idx_status (status)`
- `INDEX idx_kb_status (kb_uuid, status)`

#### 2.4.3 chunk（文档切片表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| chunk_uuid | BINARY | 16 | NO | - | 切片唯一 ID |
| doc_uuid | BINARY | 16 | NO | - | 文档 ID |
| kb_uuid | BINARY | 16 | NO | - | 知识库 ID（冗余，便于查询） |
| content | MEDIUMTEXT | - | NO | - | 切片内容 |
| chunk_order | INT | - | NO | - | 在文档中的顺序 |
| start_char | INT | - | YES | NULL | 起始字符位置 |
| end_char | INT | - | YES | NULL | 结束字符位置 |
| page_number | INT | - | YES | NULL | PDF 页码 |
| section_title | VARCHAR | 500 | YES | NULL | 所属章节标题 |
| token_count | INT | - | NO | - | token 数量 |
| metadata | JSON | - | YES | NULL | 扩展元数据 |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |

**索引**:
- `PRIMARY KEY (chunk_uuid)`
- `INDEX idx_doc (doc_uuid, chunk_order)`
- `INDEX idx_kb (kb_uuid)`
- `INDEX idx_section (section_title(100))`

---

### 2.5 检索与质量日志表

#### 2.5.1 retrieval_log（检索日志表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| retrieval_id | BIGINT | - | NO | AUTO_INCREMENT | 检索 ID |
| session_uuid | BINARY | 16 | NO | - | 会话 ID |
| message_uuid | BINARY | 16 | NO | - | 消息 ID |
| user_id | BINARY | 16 | NO | - | 用户 ID（冗余） |
| query | TEXT | - | NO | - | 原始问题 |
| rewritten_query | TEXT | - | YES | NULL | 改写后的问题 |
| retrieval_strategy | VARCHAR | 50 | YES | NULL | vector/keyword/hybrid |
| top_k | INT | - | NO | 10 | 请求数量 |
| filter_expr | TEXT | - | YES | NULL | 过滤表达式 |
| chunks_before_filter | INT | - | YES | NULL | 过滤前数量 |
| chunks_after_filter | INT | - | YES | NULL | 过滤后数量 |
| rerank_used | BOOLEAN | - | NO | FALSE | 是否使用重排 |
| rerank_model | VARCHAR | 100 | YES | NULL | 重排模型 |
| context_tokens | INT | - | YES | NULL | 上下文 token 数 |
| quality_triggered | BOOLEAN | - | NO | FALSE | 是否触发质量检查 |
| retry_count | INT | - | NO | 0 | 重试次数 |
| final_answer_length | INT | - | YES | NULL | 最终答案长度 |
| total_duration_ms | INT | - | YES | NULL | 总耗时 |
| retrieval_duration_ms | INT | - | YES | NULL | 检索耗时 |
| generation_duration_ms | INT | - | YES | NULL | 生成耗时 |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |

**索引**:
- `PRIMARY KEY (retrieval_id)`
- `INDEX idx_session (session_uuid, created_at DESC)`
- `INDEX idx_message (message_uuid)`
- `INDEX idx_user (user_id, created_at)`
- `INDEX idx_strategy (retrieval_strategy)`
- `INDEX idx_created_at (created_at)`

#### 2.5.2 retrieval_result（检索结果表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| result_id | BIGINT | - | NO | AUTO_INCREMENT | 结果 ID |
| retrieval_id | BIGINT | - | NO | - | 检索 ID |
| chunk_uuid | BINARY | 16 | NO | - | 切片 ID |
| doc_uuid | BINARY | 16 | YES | NULL | 文档 ID |
| kb_uuid | BINARY | 16 | YES | NULL | 知识库 ID |
| vector_score | FLOAT | - | YES | NULL | 向量相似度分数 |
| keyword_score | FLOAT | - | YES | NULL | 关键词匹配分数 |
| hybrid_score | FLOAT | - | YES | NULL | 混合分数 |
| rerank_score | FLOAT | - | YES | NULL | 重排分数 |
| final_score | FLOAT | - | YES | NULL | 最终分数 |
| rank | INT | - | NO | - | 排序位置 |

**索引**:
- `PRIMARY KEY (result_id)`
- `INDEX idx_retrieval (retrieval_id, rank)`
- `INDEX idx_chunk (chunk_uuid)`
- `INDEX idx_retrieval_score (retrieval_id, final_score DESC)`

**分区建议**（按月份分区，高增长表）:
```sql
ALTER TABLE retrieval_result 
PARTITION BY RANGE (YEAR(created_at) * 100 + MONTH(created_at)) (
    PARTITION p202604 VALUES LESS THAN (202605),
    PARTITION p202605 VALUES LESS THAN (202606),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
```

#### 2.5.3 quality_log（质量评估日志表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| quality_id | BIGINT | - | NO | AUTO_INCREMENT | 质量 ID |
| session_uuid | BINARY | 16 | NO | - | 会话 ID |
| message_uuid | BINARY | 16 | NO | - | 消息 ID |
| retrieval_id | BIGINT | - | YES | NULL | 关联的检索 ID |
| query | TEXT | - | NO | - | 问题 |
| rewritten_query | TEXT | - | YES | NULL | 改写后问题 |
| retrieval_strategy | VARCHAR | 50 | YES | NULL | 检索策略 |
| chunks_retrieved | INT | - | NO | 0 | 检索到的 chunk 数 |
| answer | MEDIUMTEXT | - | NO | - | 生成的答案 |
| answer_length | INT | - | YES | NULL | 答案长度 |
| context_tokens | INT | - | YES | NULL | 上下文 token 数 |
| quality_score | FLOAT | - | YES | NULL | 总分（0-1） |
| relevance_score | FLOAT | - | YES | NULL | 相关性（0-1） |
| groundedness_score | FLOAT | - | YES | NULL | groundedness（0-1） |
| completeness_score | FLOAT | - | YES | NULL | 完整性（0-1） |
| factuality_score | FLOAT | - | YES | NULL | 事实性（0-1） |
| quality_passed | BOOLEAN | - | YES | NULL | 是否通过 |
| should_retry | BOOLEAN | - | YES | NULL | 是否应重试 |
| retry_count | INT | - | NO | 0 | 实际重试次数 |
| fallback_used | BOOLEAN | - | NO | FALSE | 是否使用 fallback |
| issues | JSON | - | YES | NULL | 问题列表 |
| total_duration_ms | INT | - | YES | NULL | 总耗时 |
| retrieval_duration_ms | INT | - | YES | NULL | 检索耗时 |
| generation_duration_ms | INT | - | YES | NULL | 生成耗时 |
| quality_check_duration_ms | INT | - | YES | NULL | 质量检查耗时 |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |

**索引**:
- `PRIMARY KEY (quality_id)`
- `INDEX idx_session (session_uuid, created_at DESC)`
- `INDEX idx_message (message_uuid)`
- `INDEX idx_retrieval (retrieval_id)`
- `INDEX idx_quality_score (quality_score)`
- `INDEX idx_passed (quality_passed)`
- `INDEX idx_created_at (created_at)`

---

### 2.6 反馈与评估表

#### 2.6.1 feedback（用户反馈表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| feedback_id | BIGINT | - | NO | AUTO_INCREMENT | 反馈 ID |
| message_uuid | BINARY | 16 | NO | - | 消息 ID |
| user_id | BINARY | 16 | NO | - | 用户 ID |
| rating | TINYINT | - | YES | NULL | 评分 1-5 |
| helpful | BOOLEAN | - | YES | NULL | 是否有帮助 |
| feedback_type | VARCHAR | 50 | YES | 'rating' | rating/text/mixed |
| comment | TEXT | - | YES | NULL | 文字评论 |
| feedback_details | JSON | - | YES | NULL | 详细反馈 |
| is_flagged | BOOLEAN | - | NO | FALSE | 是否被标记（需要审核） |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |

**索引**:
- `PRIMARY KEY (feedback_id)`
- `INDEX idx_message (message_uuid)`
- `INDEX idx_user (user_id, created_at DESC)`
- `INDEX idx_rating (rating)`
- `INDEX idx_created_at (created_at)`

---

## 3. OSS 对象存储设计

### 3.1 OSS 服务配置

```python
# config/settings.py
class OSSConfig:
    # OSS 配置
    oss_endpoint = os.getenv("OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com")
    oss_access_key_id = os.getenv("OSS_ACCESS_KEY_ID")
    oss_access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
    
    # 存储桶配置
    oss_bucket_documents = os.getenv("OSS_BUCKET_DOCUMENTS", "myagent-documents")
    oss_bucket_exports = os.getenv("OSS_BUCKET_EXPORTS", "myagent-exports")
    oss_bucket_temp = os.getenv("OSS_BUCKET_TEMP", "myagent-temp")
    
    # CDN 配置
    oss_cdn_domain = os.getenv("OSS_CDN_DOMAIN", "cdn.myagent.com")
```

### 3.2 OSS 目录结构

```
oss_bucket_documents/
├── users/                          # 用户文件
│   └── {user_id}/
│       └── knowledge_bases/        # 知识库文件
│           └── {kb_uuid}/
│               └── documents/      # 文档文件
│                   └── {doc_uuid}/
│                       ├── original/           # 原始文件
│                       │   └── {original_filename}
│                       ├── processed/          # 处理中间文件
│                       │   ├── text.txt        # 提取的纯文本
│                       │   └── metadata.json   # 提取的元数据
│                       └── preview/            # 预览文件
│                           └── thumbnail.png   # 缩略图
│
├── exports/                        # 导出文件
│   └── {user_id}/
│       └── {export_type}/          # report/feedback/backup
│           └── {export_id}/
│               └── {filename}
│
└── temp/                           # 临时文件
    └── {session_id}/
        └── {temp_file}
```

### 3.3 OSS 文件命名规范

| 文件类型 | 命名规则 | 示例 |
|---------|---------|------|
| 原始文档 | `{user_id}/{kb_uuid}/{doc_uuid}/original/{timestamp}_{filename}` | `abc123/kb001/doc001/original/1714567890_report.pdf` |
| 提取文本 | `{user_id}/{kb_uuid}/{doc_uuid}/processed/text.txt` | `abc123/kb001/doc001/processed/text.txt` |
| 缩略图 | `{user_id}/{kb_uuid}/{doc_uuid}/preview/thumbnail.png` | `abc123/kb001/doc001/preview/thumbnail.png` |
| 导出报告 | `{user_id}/exports/report/{timestamp}_{type}.xlsx` | `abc123/exports/report/1714567890_quality_report.xlsx` |

### 3.4 OSS 服务函数接口

| 函数名 | 参数 | 返回值 | 功能说明 |
|--------|------|--------|---------|
| `upload_document` | `user_id: bytes`, `kb_uuid: bytes`, `doc_uuid: bytes`, `file: bytes`, `filename: str` | `oss_path: str` | 上传原始文档 |
| `upload_processed_file` | `user_id: bytes`, `kb_uuid: bytes`, `doc_uuid: bytes`, `file_type: str`, `content: bytes` | `oss_path: str` | 上传处理中间文件 |
| `upload_thumbnail` | `user_id: bytes`, `kb_uuid: bytes`, `doc_uuid: bytes`, `image: bytes` | `oss_path: str` | 上传缩略图 |
| `get_document_url` | `oss_path: str`, `expires: int = 3600` | `signed_url: str` | 获取文档下载链接（带签名） |
| `get_document` | `oss_path: str` | `bytes` | 下载文档内容 |
| `delete_document` | `oss_path: str` | `bool` | 删除文档（包括所有子文件） |
| `delete_user_documents` | `user_id: bytes` | `int` | 删除用户的所有文档 |
| `upload_export_file` | `user_id: bytes`, `export_type: str`, `filename: str`, `content: bytes` | `oss_path: str` | 上传导出文件 |
| `get_presigned_url` | `oss_path: str`, `mode: str = 'get'`, `expires: int = 3600` | `signed_url: str` | 获取预签名 URL |

---

## 4. Milvus 向量数据库设计

基于 `/data3/zb/MyAgent/backend/database/milvus/milvus_service.py` 的实际实现

### 4.1 Collection 命名规范

```
collection 命名：{user_id}_{knowledge_base_id}

示例:
- user001_kb001          # 用户 user001 的知识库 kb001
- user002_kb002          # 用户 user002 的知识库 kb002
```

**设计说明**:
- Collection 按用户 + 知识库维度隔离
- 支持动态创建，无需预先规划
- 前端选择知识库时，直接指定 collection_name

### 4.2 Milvus Schema 设计

```python
# Milvus Collection Schema (来自 milvus_service.py)
schema = MilvusClient.create_schema(enable_dynamic_field=True)

# 主键
schema.add_field("chunk_id", DataType.VARCHAR, max_length=64, is_primary=True)

# 文档结构
schema.add_field("doc_id", DataType.VARCHAR, max_length=128)       # document.doc_uuid
schema.add_field("job_id", DataType.VARCHAR, max_length=128)       # 批次任务 ID
schema.add_field("chunk_index", DataType.INT64)                    # chunk.chunk_order

# 文本内容 (支持中文分词和匹配)
schema.add_field(
    "content",
    DataType.VARCHAR,
    max_length=32768,
    enable_analyzer=True,
    analyzer_params={"type": "chinese"},
    enable_match=True,
)

# 向量字段
schema.add_field("dense", DataType.FLOAT_VECTOR, dim=1536)         # 稠密向量
schema.add_field("sparse_bm25", DataType.SPARSE_FLOAT_VECTOR)     # BM25 稀疏向量

# 用户自定义 metadata (可选)
# 示例：
# schema.add_field("knowledge_base_id", DataType.VARCHAR, max_length=512, nullable=True)
# schema.add_field("doc_status", DataType.VARCHAR, max_length=512, nullable=True)
```

**动态字段**: `enable_dynamic_field=true`，支持额外 metadata 自动写入，无需预先定义

### 4.3 Index 设计

```python
# 索引配置 (来自 milvus_service.py)
index_params = MilvusClient.prepare_index_params()

# Dense 向量索引 (HNSW)
index_params.add_index(
    field_name="dense",
    index_name="dense_hnsw",
    index_type="HNSW",
    metric_type="IP",  # Inner Product
    params={"M": 16, "efConstruction": 200},
)

# BM25 稀疏向量索引
index_params.add_index(
    field_name="sparse_bm25",
    index_name="sparse_bm25_idx",
    index_type="SPARSE_WAND",
    metric_type="BM25",
)

# 元数据索引（可选，用于过滤加速）
# index_params.add_index(
#     field_name="knowledge_base_id",
#     index_type="INVERTED",
# )
```

### 4.4 混合检索策略

**1. Dense + BM25 混合检索**
```python
# 检索流程
results = milvus_service.hybrid_search(
    collection_name="user001_kb001",
    query="用户问题",
    top_k=10,
    filter_expr='doc_id == "doc_12345"',  # 可选：按文档过滤
    ranker="RRF",  # 或 "Weight"
    hybrid_alpha=0.5,  # Dense 权重 (0-1)
    group_by_field="doc_id",  # 按文档分组，避免单文档占满
    group_size=1,  # 每组返回 1 条
)
```

**2. 纯向量检索**
```python
results = milvus_service.vector_search(
    collection_name="user001_kb001",
    query="用户问题",
    top_k=10,
    filter_expr='knowledge_base_id == "kb001"',  # 可选过滤
)
```

**3. 纯关键词检索 (BM25)**
```python
results = milvus_service.keyword_search(
    collection_name="user001_kb001",
    query="关键词",
    top_k=10,
    filter_expr=None,
    use_text_match_filter=False,  # True: 先用 TEXT_MATCH 预过滤
)
```

### 4.5 数据写入流程

```
文档上传到 OSS
    │
    ▼
提取文本 + 元数据
    │
    ▼
文档切片 (chunk)
    │
    ▼
生成 embedding (dense) ← 自动调用 embedding_service
    │
    ▼
计算 BM25 索引 (sparse_bm25) ← 自动通过 BM25 function
    │
    ▼
写入 MySQL chunk 表
    │
    ▼
写入 Milvus (upsert_chunks)
    │
    ▼
更新 document 表 status = done
```

**写入代码示例**:
```python
# 准备切片数据
chunks = [
    {
        "chunk_id": "uuid1",
        "doc_id": "doc_12345",
        "job_id": "job_67890",
        "chunk_index": 0,
        "content": "切片文本内容",
        "metadata": {
            "knowledge_base_id": "kb001",
            "page_number": 1,
            "section_title": "第一章",
        }
    },
    # ... 更多切片
]

# 写入 Milvus
result = milvus_service.upsert_chunks(
    collection_name="user001_kb001",
    chunks=chunks,
    vector_dim=1536,
    embedding_model="text-embedding-3-small",
    metadata_fields=[
        {"key": "knowledge_base_id", "fulltext": False, "index": True},
        {"key": "page_number", "fulltext": False, "index": True},
    ]
)
```

### 4.6 数据删除策略

```python
# 按任务 ID 删除 (批量删除)
milvus_service.delete_by_job(collection_name, job_id="job_67890")

# 按文档 ID 删除
milvus_service.delete_by_doc_id(collection_name, doc_id="doc_12345")

# 按切片 ID 删除 (精确删除)
milvus_service.delete_by_chunk_ids(collection_name, chunk_ids=["uuid1", "uuid2"])
```

### 4.7 Filter 表达式语法

```python
# 精确匹配
filter_expr = 'doc_id == "doc_12345"'

# IN 表达式
filter_expr = 'doc_id in ["doc_1", "doc_2", "doc_3"]'

# 组合条件
filter_expr = 'doc_id == "doc_12345" and knowledge_base_id == "kb001"'

# 文本匹配 (TEXT_MATCH)
filter_expr = 'TEXT_MATCH(content, "关键词")'

# 组合文本匹配
filter_expr = '(knowledge_base_id == "kb001") and TEXT_MATCH(content, "人工智能")'
```

**注意事项**:
- 字符串值需要用双引号包裹
- 特殊字符需要转义：`escaped = doc_id.replace('"', '\\"')`
- 支持 AND/OR 逻辑组合

### 4.8 与 MySQL 的协作

**数据流向**:
1. **文档上传** → MySQL `document` 表记录元数据
2. **切片嵌入** → Milvus Collection 存储向量
3. **用户检索** → 前端选择知识库 → API 传入 filter 条件 → Milvus 返回相关切片
4. **答案生成** → LLM 结合检索结果生成回答
5. **会话记录** → MySQL `session` 和 `message` 表记录对话

**关键设计**:
- session 表**不存储** knowledge_base_ids 或 document_ids
- 检索时通过 `filter_expr` 动态指定知识库/文档范围
- Collection 按 `{user_id}_{knowledge_base_id}` 命名，天然隔离
- MySQL 存储业务元数据，Milvus 专注向量检索

---

## 5. 文档处理流程存储设计

### 5.1 文档处理状态机

```
┌─────────┐     ┌─────────────┐     ┌────────┐     ┌────────┐
│ pending │ ──→ │ processing  │ ──→ │  done  │ ──→ │  done  │
└─────────┘     └─────────────┘     └────────┘     └────────┘
     │                │                    │
     │                │                    │
     │                ▼                    ▼
     │           ┌────────┐          ┌──────────┐
     └──────────→│ failed │          │ disabled │
                 └────────┘          └──────────┘
```

### 5.2 文档处理各阶段存储操作

| 阶段 | MySQL 操作 | OSS 操作 | Milvus 操作 |
|------|----------|---------|------------|
| **1. 上传** | `INSERT INTO document (status=pending)` | `upload_document()` | - |
| **2. 开始处理** | `UPDATE document SET status=processing` | - | - |
| **3. 提取文本** | - | `upload_processed_file(text.txt)` | - |
| **4. 切片** | `INSERT INTO chunk (多条)` | - | - |
| **5. Embedding** | - | - | `upsert_chunks()` |
| **6. 完成** | `UPDATE document SET status=done, chunk_count=N` | - | - |

### 5.3 文档处理记录表（新增）

#### 5.3.1 document_processing_log（文档处理日志表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| log_id | BIGINT | - | NO | AUTO_INCREMENT | 日志 ID |
| doc_uuid | BINARY | 16 | NO | - | 文档 ID |
| stage | VARCHAR | 50 | NO | - | 处理阶段 |
| status | VARCHAR | 20 | NO | - | success/failure |
| started_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 开始时间 |
| completed_at | TIMESTAMP | - | YES | NULL | 完成时间 |
| duration_ms | BIGINT | - | YES | NULL | 耗时（毫秒） |
| error_message | TEXT | - | YES | NULL | 错误信息 |
| metadata | JSON | - | YES | NULL | 阶段元数据 |

**索引**:
- `PRIMARY KEY (log_id)`
- `INDEX idx_doc (doc_uuid, started_at DESC)`
- `INDEX idx_stage (stage, status)`

---

## 6. 知识库管理存储设计

### 6.1 知识库权限表

#### 6.1.1 kb_permission（知识库权限表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| permission_id | BIGINT | - | NO | AUTO_INCREMENT | 权限 ID |
| kb_uuid | BINARY | 16 | NO | - | 知识库 ID |
| user_id | BINARY | 16 | NO | - | 用户 ID |
| permission_level | VARCHAR | 20 | NO | - | owner/admin/editor/viewer |
| granted_by | BINARY | 16 | YES | NULL | 授权人 ID |
| granted_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 授权时间 |

**索引**:
- `PRIMARY KEY (permission_id)`
- `UNIQUE KEY uk_kb_user (kb_uuid, user_id)`
- `INDEX idx_user (user_id)`

### 6.2 知识库使用统计

#### 6.2.1 kb_usage_stats（知识库使用统计表）

| 字段名 | 类型 | 长度 | 允许 NULL | 默认值 | 说明 |
|--------|------|------|----------|--------|------|
| stat_id | BIGINT | - | NO | AUTO_INCREMENT | 统计 ID |
| kb_uuid | BINARY | 16 | NO | - | 知识库 ID |
| stat_date | DATE | - | NO | - | 统计日期 |
| query_count | INT | - | NO | 0 | 查询次数 |
| unique_users | INT | - | NO | 0 | 独立用户数 |
| avg_quality_score | FLOAT | - | YES | NULL | 平均质量分 |
| total_tokens | BIGINT | - | NO | 0 | 总 token 消耗 |
| created_at | TIMESTAMP | - | NO | CURRENT_TIMESTAMP | 创建时间 |

**索引**:
- `PRIMARY KEY (stat_id)`
- `UNIQUE KEY uk_kb_date (kb_uuid, stat_date)`
- `INDEX idx_date (stat_date)`

---

## 7. 跨存储系统关系图

### 7.1 完整数据流关系

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        用户上传文档                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  MySQL: document (status=pending)                                        │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ doc_uuid | kb_uuid | original_filename | oss_path | status=pending│  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  OSS: 上传原始文件                                                        │
│  oss://bucket/users/{user_id}/kb/{kb_uuid}/doc/{doc_uuid}/original/...  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  文档处理流水线                                                           │
│  1. 提取文本 → OSS: processed/text.txt                                   │
│  2. 文档切片 → MySQL: chunk (多条)                                       │
│  3. 生成向量 → Milvus: upsert                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  MySQL: document (status=done, chunk_count=N)                            │
│  MySQL: chunk (chunk_uuid, doc_uuid, content, token_count)               │
│  Milvus: {chunk_id, doc_id, kb_id, content, dense, sparse_bm25}          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        用户提问                                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Milvus: hybrid_search (dense + BM25)                                    │
│  返回：chunk_id, doc_id, kb_id, content, score                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  MySQL: retrieval_log (记录检索过程)                                       │
│  MySQL: retrieval_result (记录每个 chunk 的分数)                            │
│  MySQL: quality_log (记录质量评估)                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  MySQL: message (记录问答内容)                                             │
│  MySQL: short_term_memory (提取短期记忆)                                   │
│  MySQL: long_term_memory (可能触发长期记忆)                                │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.2 外键关系图

```
user
  │
  ├─────────────┬─────────────┬─────────────┐
  ▼             ▼             ▼             ▼
session     knowledge_base  long_term_memory  feedback
  │             │
  │             ├─────────────┐
  │             ▼             ▼
  │           document    kb_permission
  │             │
  │             ▼
  │           chunk
  │             │
  └─────────────┼─────────────┐
                ▼             ▼
          retrieval_log  retrieval_result
                │
                ▼
          quality_log
                │
                ▼
          message ─────→ feedback
```

### 7.3 数据生命周期

| 数据类型 | 存储位置 | 保留周期 | 归档策略 |
|---------|---------|---------|---------|
| 原始文档 | OSS | 永久（用户删除前） | - |
| 处理中间文件 | OSS | 30 天 | 自动清理 |
| 切片内容 | MySQL + Milvus | 永久（文档删除前） | - |
| 检索日志 | MySQL | 90 天 | 归档到历史表 |
| 质量日志 | MySQL | 180 天 | 归档到历史表 |
| 短期记忆 | MySQL | 会话 + 30 天 | 自动过期 |
| 长期记忆 | MySQL | 永久（用户删除前） | - |
| 反馈数据 | MySQL | 永久 | - |
| 统计报表 | OSS | 永久 | - |

---

## 8. 数据迁移与备份策略

### 8.1 备份方案

| 数据类型 | 备份频率 | 保留周期 | 备份方式 |
|---------|---------|---------|---------|
| MySQL | 每天 | 30 天 | 全量备份 + binlog |
| Milvus | 每天 | 7 天 | 快照备份 |
| OSS | 实时 | 永久 | 跨区域复制 |

### 8.2 数据迁移流程

```
1. MySQL 导出
   mysqldump --single-transaction knowledge_agent > backup.sql

2. Milvus 导出
   - 使用 Milvus Backup 工具
   - 或导出为 Parquet 格式

3. OSS 导出
   - 使用 ossutil 批量下载
   - 或配置生命周期规则自动归档到 OSS Archive

4. 恢复流程
   - 先恢复 MySQL（基础数据）
   - 再恢复 Milvus（向量数据）
   - 最后验证 OSS 文件完整性
```

---

## 总结

本文档提供了完整的持久化与存储设计方案：

1. **MySQL**: 12 张核心表，覆盖用户、会话、记忆、知识库、文档、日志、反馈
2. **OSS**: 3 个存储桶，支持文档、导出、临时文件的完整管理
3. **Milvus**: Collection 设计、Schema 定义、Index 配置
4. **数据流**: 文档处理、问答检索、记忆提取的完整流程
5. **生命周期**: 数据保留、归档、备份策略

所有设计遵循**不修改现有代码**原则，通过新增表和接口实现功能扩展。
