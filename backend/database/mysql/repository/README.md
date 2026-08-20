# Repository 层使用指南

## 目录结构

```
repository/
├── __init__.py                       # 包初始化，导出所有 Repository
├── base_repository.py                # Repository 基类（含软删除）
├── soft_delete_mixin.py              # 软删除 Mixin
├── user_repository.py                # 用户表 Repository
├── session_repository.py             # 会话表 Repository
├── message_repository.py             # 消息表 Repository
├── knowledge_base_repository.py      # 知识库表 Repository
├── document_repository.py            # 文档表 Repository
├── chunk_repository.py               # 切片表 Repository
├── short_term_memory_repository.py   # 短期记忆 Repository（时间衰减权重）
└── long_term_memory_repository.py    # 长期记忆 Repository（MySQL+Milvus）
```

## 设计原则

1. **单一职责**：每个 Repository 只负责一张表的 CRUD 操作
2. **UUID 统一**：所有 ID 使用 CHAR(36) UUID 字符串格式
3. **软删除支持**：所有 Repository 继承 `SoftDeleteMixin`，支持软删除
4. **时间衰减**：短期记忆使用时间衰减权重，而非过期删除
5. **双存储支持**：长期记忆 Repository 同时支持 MySQL 和 Milvus

## UUID 使用规范

### 统一格式：CHAR(36) 字符串

**生成 UUID（推荐）:**
```python
import uuid

# ✅ 正确：UUID 字符串
user_id = str(uuid.uuid4())  # '550e8400-e29b-41d4-a716-446655440000'
```

**不要使用:**
```python
# ❌ 错误：bytes 格式
user_id = uuid.uuid4().bytes

# ❌ 错误：hex 格式
user_id = uuid.uuid4().hex
```

### 所有 Repository 调用示例

```python
# 插入时使用 UUID 字符串
user_repo.insert({
    'user_id': str(uuid.uuid4()),
    'username': 'john',
    'password_hash': 'hashed_password'
})

# 查询时使用 UUID 字符串
user = user_repo.find_one({'user_id': '550e8400-e29b-41d4-a716-446655440000'})
```

## 使用方式

### 1. 初始化 Repository

```python
from config.settings import Settings
from database.mysql.mysql_client import MysqlClient
from database.mysql.repository import get_repositories

# 创建数据库客户端
settings = Settings()
db_client = MysqlClient(settings)

# 获取所有 Repository（可选：传入 milvus_client）
repositories = get_repositories(db_client)
user_repo = repositories['user']
session_repo = repositories['session']
```

### 2. 通用 CRUD 方法（从 BaseRepository 继承）

```python
# 插入单条记录
user_repo.insert({
    'user_id': str(uuid.uuid4()),
    'username': 'john',
    'password_hash': 'hashed_password'
})

# 批量插入
user_repo.insert_batch([
    {'user_id': str(uuid.uuid4()), 'username': 'john'},
    {'user_id': str(uuid.uuid4()), 'username': 'jane'}
])

# 更新记录
user_repo.update(
    {'user_id': 'uuid-string'},
    {'status': 0}  # 禁用用户
)

# 软删除（推荐）
user_repo.soft_delete({'user_id': 'uuid-string'})

# 物理删除（慎用）
user_repo.delete({'user_id': 'uuid-string'})

# 查询单条（默认排除软删除）
user = user_repo.find_one({'username': 'john'})

# 条件查询（默认排除软删除）
users = user_repo.find_by(
    {'status': 1},
    fields='user_id, username, email',
    order_by='created_at DESC',
    limit=20
)

# 查询所有（默认排除软删除）
all_users = user_repo.find_all(order_by='created_at DESC', limit=100)

# 包含软删除的数据
all_users = user_repo.find_all(exclude_deleted=False)

# 统计数量
count = user_repo.count({'status': 1})
```

### 3. 短期记忆 Repository（时间衰减权重）

```python
from database.mysql.repository import get_repositories
import uuid

repositories = get_repositories(db_client)
stm_repo = repositories['short_term_memory']

# 创建短期记忆（长期存储，使用时间衰减权重）
stm_repo.create_memory(
    session_uuid=str(uuid.uuid4()),
    user_id=user_id,
    query_summary='用户问了什么',
    answer_summary='助手回答了什么',
    entities={'person': ['张三'], 'org': ['公司 A']},
    base_relevance_score=0.9  # 基础相关性分数
)

# 搜索短期记忆（自动计算时间衰减权重）
memories = stm_repo.search_memories(
    session_uuid=session_id,
    query='关键词',
    top_k=10,
    days_decay_factor=0.95  # 每天衰减 5%
)

# 返回的记忆包含得分信息
for m in memories:
    print(f"Memory: {m['memory_id']}")
    print(f"  Base Score: {m['base_relevance_score']}")
    print(f"  Time Weight: {m['time_decay_weight']}")
    print(f"  Final Score: {m['final_score']}")

# 获取会话的所有记忆（按得分排序）
memories = stm_repo.get_session_memories(session_id, limit=50)

# 获取用于上下文的记忆
memories = stm_repo.get_memories_for_context(
    user_id=user_id,
    context_size=20,
    min_score=0.3  # 最小得分阈值
)
```

### 4. 长期记忆 Repository（MySQL + Milvus）

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
    memory_type='preference',
    top_k=5
)

# 更新记忆
ltm_repo.update_memory(memory_id, content='用户喜欢 Python 和 Rust')

# 删除记忆（软删除 + Milvus 删除）
ltm_repo.delete_memory(memory_id)

# 按类型获取记忆
memories = ltm_repo.get_memories_by_type(user_id, 'preference', limit=100)

# 按分类获取记忆
memories = ltm_repo.get_memories_by_category(user_id, '技术偏好', limit=100)
```

## 时间衰减权重说明

### 算法公式

```python
# 时间衰减权重
time_weight = days_decay_factor ^ days_elapsed

# 综合得分
final_score = base_relevance * time_weight * access_bonus

# 访问次数奖励
access_bonus = 1 + 0.1 * log(access_count + 1)
```

### 示例

| 天数 | 时间权重 (0.95^n) | 说明 |
|------|-----------------|------|
| 1 天 | 0.95 | 几乎完整权重 |
| 7 天 | 0.70 | 保留 70% 权重 |
| 30 天 | 0.21 | 权重明显降低 |
| 90 天 | 0.10 | 最低权重（不再降低） |

### 配置参数

可在 `system_config` 表调整参数：

```sql
UPDATE system_config 
SET config_value = '{"value": 0.95}'
WHERE config_key = 'memory_time_decay_factor';
```

## 注意事项

1. **UUID 格式统一**：所有 ID 使用 `str(uuid.uuid4())`，不要用 bytes 或 hex
2. **软删除**：默认查询排除软删除的数据，如需包含使用 `exclude_deleted=False`
3. **长期记忆**：必须传入 `milvus_client` 才能使用双存储功能
4. **短期记忆**：长期存储，按时间衰减权重排序，不会自动删除
