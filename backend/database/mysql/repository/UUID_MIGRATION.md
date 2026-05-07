# Repository 层 UUID 格式迁移指南

## 概述

本次迁移将所有 Repository 的 UUID 格式从 `BINARY(16)` 统一改为 `CHAR(36)` 字符串格式。

## 迁移内容

### 数据库层面

**修改前：**
```sql
user_id BINARY(16) PRIMARY KEY
session_uuid BINARY(16) PRIMARY KEY
```

**修改后：**
```sql
user_id CHAR(36) PRIMARY KEY
session_uuid CHAR(36) PRIMARY KEY
```

### Repository 层面

**修改前：**
```python
# 使用 bytes 格式
user_id = uuid.uuid4().bytes
session_id = uuid.uuid4().bytes

# 函数参数类型
def get_by_id(self, user_id: bytes) -> Optional[Dict[str, Any]]:
```

**修改后：**
```python
# 使用字符串格式
user_id = str(uuid.uuid4())
session_id = str(uuid.uuid4())

# 函数参数类型
def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
```

## 已修改的文件

### 1. database_schema.py
- 所有 UUID 字段从 `BINARY(16)` 改为 `CHAR(36)`
- 更新了表注释说明 UUID 格式

### 2. Repository 文件（批量修改）
- ✅ `user_repository.py`
- ✅ `session_repository.py`
- ✅ `message_repository.py`
- ✅ `knowledge_base_repository.py`
- ✅ `long_term_memory_repository.py`（已使用字符串格式）
- ✅ `short_term_memory_repository.py`（已使用字符串格式）

### 3. 已正确的文件（无需修改）
- ✅ `document_repository.py` - 已使用字符串格式
- ✅ `chunk_repository.py` - 已使用字符串格式

## 代码变更示例

### UserRepository

```python
# 修改前
def create_user(self, username: str, password_hash: str, ...) -> Dict[str, Any]:
    user_id = uuid.uuid4().bytes  # ❌ bytes 格式
    data = {'user_id': user_id, ...}
    logger.info(f"user_id: {user_id.hex}")  # ❌ 使用 .hex

def get_by_id(self, user_id: bytes) -> Optional[Dict[str, Any]]:  # ❌ bytes 参数
    return self.find_one({'user_id': user_id})

# 修改后
def create_user(self, username: str, password_hash: str, ...) -> Dict[str, Any]:
    user_id = str(uuid.uuid4())  # ✅ 字符串格式
    data = {'user_id': user_id, ...}
    logger.info(f"user_id: {user_id}")  # ✅ 直接打印

def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:  # ✅ str 参数
    return self.find_one({'user_id': user_id})
```

### SessionRepository

```python
# 修改前
def create_session(self, user_id: bytes, ...) -> Dict[str, Any]:  # ❌ bytes
    session_id = uuid.uuid4().bytes  # ❌ bytes
    logger.info(f"user_id={user_id.hex}, session_id={session_id.hex}")  # ❌ .hex

# 修改后
def create_session(self, user_id: str, ...) -> Dict[str, Any]:  # ✅ str
    session_id = str(uuid.uuid4())  # ✅ str
    logger.info(f"user_id={user_id}, session_id={session_id}")  # ✅ 直接打印
```

## 迁移步骤

### 1. 备份数据库

```bash
mysqldump -u [user] -p [database_name] > backup_before_uuid_migration.sql
```

### 2. 修改表结构

```sql
-- 方式 1: 重建表（推荐，数据量小时）
DROP TABLE IF EXISTS user;
-- 使用新的 DDL 创建表
source database_schema.sql;

-- 方式 2: 转换字段类型（数据量大时）
-- 注意：需要先导出 BINARY(16) 数据，转换为字符串，再导入
ALTER TABLE user 
MODIFY user_id CHAR(36) PRIMARY KEY;
```

### 3. 数据迁移（如果需要）

```python
import uuid
import pymysql

def binary_to_uuid(binary_uuid: bytes) -> str:
    """将 BINARY(16) 转换为 UUID 字符串"""
    return str(uuid.UUID(bytes=binary_uuid))

def migrate_table(cursor, table_name, id_column):
    """迁移单个表的数据"""
    # 查询旧数据
    cursor.execute(f"SELECT {id_column}, * FROM {table_name}")
    rows = cursor.fetchall()
    
    for row in rows:
        old_id = row[0]
        new_id = binary_to_uuid(old_id)
        
        # 更新为新 ID
        cursor.execute(
            f"UPDATE {table_name} SET {id_column} = %s WHERE {id_column} = %s",
            (new_id, old_id)
        )

# 主迁移逻辑
conn = pymysql.connect(...)
cursor = conn.cursor()

tables = ['user', 'session', 'message', 'knowledge_base', 'document', 'chunk']
for table in tables:
    migrate_table(cursor, table, 'id_column_name')

conn.commit()
```

### 4. 更新 Repository 代码

所有 Repository 文件的修改已通过脚本批量完成，包括：
- `uuid.uuid4().bytes` → `str(uuid.uuid4())`
- `.hex` → 移除（直接打印字符串）
- `: bytes` → `: str`（类型注解）

### 5. 验证迁移

```python
# 测试创建和查询
from database.mysql.repository import get_repositories

repositories = get_repositories(db_client)
user_repo = repositories['user']

# 创建用户
user = user_repo.create_user(
    username='test_user',
    password_hash='hashed_password'
)

# 验证 ID 格式
print(f"User ID: {user['user_id']}")  # 应该是 UUID 字符串
print(f"ID Type: {type(user['user_id'])}")  # 应该是 <class 'str'>

# 查询用户
retrieved = user_repo.get_by_id(user['user_id'])
assert retrieved is not None
```

## 常见问题

### Q1: 为什么要改为 CHAR(36) 而不是 BINARY(16)？

**A:** 
1. **统一性**：避免 bytes/hex/字符串混用导致的类型错误
2. **调试友好**：字符串格式便于日志记录和调试
3. **API 友好**：JSON 传输不需要额外序列化
4. **可维护性**：降低代码复杂度

### Q2: 性能影响如何？

**A:** 
- CHAR(36) 比 BINARY(16) 多占用约 20 字节（包括字符集开销）
- 对于大多数应用，这 20 字节的差异可以忽略不计
- 如果数据量超过千万级，可以考虑优化

### Q3: 如何回滚到 BINARY(16)？

**A:** 
1. 恢复数据库备份
2. 还原 Repository 代码（使用 git）
3. 修改 database_schema.py 回 BINARY(16)

## 迁移清单

- [x] database_schema.py - UUID 字段改为 CHAR(36)
- [x] user_repository.py - 修改 UUID 处理
- [x] session_repository.py - 修改 UUID 处理
- [x] message_repository.py - 修改 UUID 处理
- [x] knowledge_base_repository.py - 修改 UUID 处理
- [x] document_repository.py - 已正确（无需修改）
- [x] chunk_repository.py - 已正确（无需修改）
- [x] short_term_memory_repository.py - 已正确（无需修改）
- [x] long_term_memory_repository.py - 已正确（无需修改）
- [x] base_repository.py - 添加 UUID 格式说明
- [x] README.md - 更新文档说明
- [ ] 数据库表结构迁移（需要手动执行）
- [ ] 数据迁移（如果需要）
- [ ] 测试验证

## 注意事项

1. **不要在代码中混用格式**：统一使用 `str(uuid.uuid4())`
2. **API 层无需修改**：UUID 字符串可以直接序列化为 JSON
3. **日志记录**：可以直接打印 UUID，无需 `.hex` 转换
4. **数据库迁移**：建议先在测试环境验证

## 相关文档

- [README.md](../README.md) - 数据库设计文档
- [repository/README.md](README.md) - Repository 使用指南
