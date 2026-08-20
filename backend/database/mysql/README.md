# MySQL 数据库设计文档

## 概述

本目录包含 RAG 系统的 MySQL 数据库设计，用于知识库和文档管理系统的数据持久化。

## 核心设计原则

1. **UUID 格式统一**: 所有 ID 字段使用 `CHAR(36)` 存储 UUID 字符串，避免 hex/bytes 混用
   - 示例：`'550e8400-e29b-41d4-a716-446655440000'`
   - 生成方式：`str(uuid.uuid4())`
   - 统一格式，避免类型转换错误

2. **短期记忆策略**: 长期存储，使用时间衰减权重
   - 不是 7 天过期删除
   - 时间越久的记忆，权重越低
   - 公式：`time_weight = 0.95 ^ days_elapsed`

3. **长期记忆策略**: MySQL + Milvus 双存储
   - MySQL 存储元数据
   - Milvus 存储向量（用于语义检索）

4. **逻辑约束**: 使用应用层逻辑保证数据一致性，而非物理外键约束

## 目录结构

```
backend/database/mysql/
├── mysql_client.py              # MySQL 连接池（核心，不可修改）
├── database_schema.py           # 数据库表结构定义（DDL）
├── init_database.py             # 数据库初始化脚本
└── repository/                  # Repository 层
    ├── __init__.py              # 包导出
    ├── base_repository.py       # Repository 基类（含软删除）
    ├── soft_delete_mixin.py     # 软删除 Mixin
    ├── user_repository.py       # 用户表 Repository
    ├── session_repository.py    # 会话表 Repository
    ├── message_repository.py    # 消息表 Repository
    ├── knowledge_base_repository.py  # 知识库 Repository
    ├── document_repository.py   # 文档 Repository
    ├── chunk_repository.py      # 切片 Repository
    ├── short_term_memory_repository.py  # 短期记忆 Repository（时间衰减权重）
    └── long_term_memory_repository.py   # 长期记忆 Repository（MySQL+Milvus）
```

## 数据库表

### 核心业务表

| 表名 | ID 字段类型 | 说明 |
|------|-----------|------|
| `user` | CHAR(36) | 用户信息 |
| `session` | CHAR(36) | 对话会话 |
| `message` | CHAR(36) | 对话消息 |

### 知识库与文档表

| 表名 | ID 字段类型 | 说明 |
|------|-----------|------|
| `knowledge_base` | CHAR(36) | 知识库元数据 |
| `document` | CHAR(36) | 文档元数据 |
| `chunk` | CHAR(36) | 文档切片内容 |

### 记忆系统表

| 表名 | ID 字段类型 | 存储策略 | 权重策略 |
|------|-----------|----------|----------|
| `short_term_memory` | CHAR(36) | MySQL（长期） | 时间衰减权重 |
| `long_term_memory` | CHAR(36) | MySQL + Milvus | 重要性分数 |

### 日志与配置表

| 表名 | ID 字段类型 | 说明 |
|------|-----------|------|
| `retrieval_log` | BIGINT | 检索日志 |
| `feedback` | BIGINT | 用户反馈 |
| `document_processing_log` | BIGINT | 文档处理日志 |
| `prompt_template` | BIGINT | Prompt 模板 |
| `system_config` | VARCHAR(100) | 系统配置 |

## 快速开始

### 初始化数据库

```bash
cd backend/database/mysql

# 方式 1: 使用 Python 脚本
python init_database.py

# 方式 2: 删除现有表后重新创建（危险！）
python init_database.py --drop
```

### 在代码中使用

```python
from config.settings import Settings
from database.mysql.mysql_client import MysqlClient
from database.mysql.repository import get_repositories

# 初始化
settings = Settings()
db_client = MysqlClient(settings)
repositories = get_repositories(db_client)

# 使用 Repository
user_repo = repositories['user']
session_repo = repositories['session']
message_repo = repositories['message']

# CRUD 操作
user = user_repo.find_one({'username': 'john'})
users = user_repo.find_by({'status': 1}, limit=10)
user_repo.insert({'user_id': str(uuid.uuid4()), 'username': 'jane', ...})
user_repo.soft_delete({'user_id': user_id})  # 软删除
```

## UUID 使用规范

### 统一格式：CHAR(36) 字符串

**生成 UUID:**
```python
import uuid

# 生成 UUID 字符串（推荐）
user_id = str(uuid.uuid4())  # '550e8400-e29b-41d4-a716-446655440000'
```

**不要使用:**
```python
# ❌ 错误：bytes 格式
user_id = uuid.uuid4().bytes

# ❌ 错误：hex 格式
user_id = uuid.uuid4().hex
```

**所有 Repository 统一使用:**
```python
# ✅ 正确
session_repo.insert({
    'session_uuid': str(uuid.uuid4()),
    'user_id': user_id,  # 传入 UUID 字符串
    ...
})
```

## Repository 使用指南

### 通用 CRUD 方法

所有 Repository 继承自 `BaseRepository`，提供以下方法：

```python
# 插入单条
repo.insert({'field1': 'value1', 'field2': 'value2'})

# 批量插入
repo.insert_batch([{'field1': 'v1'}, {'field1': 'v2'}])

# 更新
repo.update({'id': 'uuid-string'}, {'field1': 'new_value'})

# 查询单条
repo.find_one({'id': 'uuid-string'})

# 条件查询
repo.find_by({'status': 1}, order_by='created_at DESC', limit=10)

# 查询所有
repo.find_all(order_by='created_at DESC')

# 软删除
repo.soft_delete({'id': 'uuid-string'})

# 物理删除（慎用）
repo.delete({'id': 'uuid-string'})

# 统计
repo.count({'status': 1})
```

### 软删除

所有业务表默认排除软删除的数据：

```python
# 查询时自动排除 deleted_at IS NOT NULL 的数据
users = user_repo.find_by({'status': 1})  # 已排除软删除

# 包含软删除的数据
users = user_repo.find_by({'status': 1}, exclude_deleted=False)

# 软删除
user_repo.soft_delete({'user_id': 'uuid-string'})

# 物理删除（慎用）
user_repo.delete({'user_id': 'uuid-string'})
```

### 短期记忆（时间衰减权重）

```python
from database.mysql.repository import get_repositories
import uuid

repositories = get_repositories(db_client)
stm_repo = repositories['short_term_memory']

# 创建短期记忆（长期存储）
stm_repo.create_memory(
    session_uuid=str(uuid.uuid4()),
    user_id=user_id,
    query_summary='用户问了什么',
    answer_summary='助手回答了什么',
    base_relevance_score=0.9  # 基础相关性分数
)

# 搜索短期记忆（自动计算时间衰减权重）
memories = stm_repo.search_memories(
    session_uuid=session_id,
    query='关键词',
    top_k=10,
    days_decay_factor=0.95  # 每天衰减 5%
)

# 获取用于上下文的记忆
memories = stm_repo.get_memories_for_context(
    user_id=user_id,
    context_size=20,
    min_score=0.3  # 最小得分阈值
)

# 每个记忆返回的字段
{
    'memory_id': 'uuid-string',
    'query_summary': '...',
    'answer_summary': '...',
    'base_relevance_score': 0.9,
    'time_decay_weight': 0.75,  # 时间衰减权重
    'final_score': 0.68  # 综合得分
}
```

### 长期记忆（MySQL+Milvus）

```python
from database.mysql.repository import get_repositories
from milvus_client import MilvusClient

# 初始化 Milvus
milvus = MilvusClient()

# 获取 Repository（传入 milvus_client）
repositories = get_repositories(db_client, milvus_client=milvus)
ltm_repo = repositories['long_term_memory']

# 创建长期记忆（同时写入 MySQL 和 Milvus）
ltm_repo.create_memory(
    user_id='uuid-string',
    memory_type='preference',  # preference/habit/fact/relationship/event
    content='用户喜欢 Python 编程',
    title='编程偏好',
    category='技术偏好',
    tags=['编程', 'Python'],
    importance_score=0.8
)

# 搜索长期记忆（使用 Milvus 向量检索）
memories = ltm_repo.search_memories(
    user_id='uuid-string',
    query='用户喜欢什么编程语言',
    top_k=5
)

# 更新记忆
ltm_repo.update_memory(memory_id, content='用户喜欢 Python 和 Rust')

# 删除记忆（软删除 + Milvus 删除）
ltm_repo.delete_memory(memory_id)
```

## 时间衰减权重算法

### 短期记忆得分计算

```python
# 时间衰减权重
time_weight = days_decay_factor ^ days_elapsed

# 例如：days_decay_factor = 0.95
# 创建后 1 天：0.95^1 = 0.95
# 创建后 7 天：0.95^7 ≈ 0.70
# 创建后 30 天：0.95^30 ≈ 0.21
# 创建后 90 天：0.95^90 ≈ 0.01 (但最低 0.1)

# 综合得分
final_score = base_relevance * time_weight * access_bonus

# access_bonus = 1 + 0.1 * log(access_count + 1)
# 访问次数越多，得分越高（有上限 2x）
```

### 配置参数

```python
# 系统配置表
memory_time_decay_factor = 0.95  # 每天衰减 5%
memory_min_weight = 0.1  # 最低权重
memory_access_weight = 0.1  # 访问次数权重
```

## 数据模型

### ID 格式统一

| 字段类型 | 数据库类型 | Python 类型 | 示例 |
|----------|-----------|-----------|------|
| UUID ID | CHAR(36) | str | `'550e8400-e29b-41d4-a716-446655440000'` |
| 自增 ID | BIGINT | int | `12345` |
| 配置键 | VARCHAR(100) | str | `'default_llm_model'` |

### 软删除策略

| 表名 | 物理删除策略 |
|------|------------|
| user | 定期清理（90 天） |
| session | 定期清理（90 天） |
| message | 定期清理（90 天） |
| document | 定期清理（90 天） |
| short_term_memory | 不清理（长期存储） |
| long_term_memory | 手动清理 |

## 性能优化

### 索引设计

- 所有 UUID 字段使用 `CHAR(36)`，统一格式
- 组合索引覆盖常用查询（如 `idx_user_status`）
- 移除冗余索引（左前缀原则）

### 时间衰减查询优化

```sql
-- 查询时直接按得分排序（应用层计算）
SELECT * FROM short_term_memory 
WHERE user_id = 'uuid'
ORDER BY created_at DESC
LIMIT 100;

-- 应用层计算得分并排序
-- 这样可以避免在 SQL 中使用复杂函数
```

## 注意事项

1. **不要修改 mysql_client.py** - 这是核心连接池，已被充分测试
2. **统一 UUID 格式** - 所有 ID 使用 `str(uuid.uuid4())`，不要用 bytes 或 hex
3. **使用软删除** - 避免物理删除，保留数据可恢复性
4. **时间衰减配置** - 可在 `system_config` 表调整衰减参数
5. **长期记忆双写** - 创建/更新/删除时需同时同步 MySQL 和 Milvus

## 相关文件

- `database_schema.py` - 完整的 DDL 语句
- `init_database.py` - 数据库初始化脚本
- `repository/` - Repository 层实现
