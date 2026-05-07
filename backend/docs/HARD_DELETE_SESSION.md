# 删除会话改为硬删除

## ✅ 修改内容

### 1. Session Repository 层

**文件**: `backend/database/mysql/repository/session_repository.py`

**修改前**（软删除）:
```python
def delete_session(self, session_id: str) -> int:
    """删除会话（软删除）"""
    return self.update(
        {'session_uuid': session_id},
        {'status': 2}
    )
```

**修改后**（硬删除）:
```python
def delete_session(self, session_id: str) -> int:
    """删除会话（硬删除）"""
    return self.execute(
        "DELETE FROM session WHERE session_uuid = %s",
        (session_id,)
    )
```

### 2. Message Repository 层

**文件**: `backend/database/mysql/repository/message_repository.py`

**新增方法**:
```python
def delete_messages_by_session(self, session_id: str) -> int:
    """删除会话的所有消息"""
    return self.execute(
        "DELETE FROM message WHERE session_uuid = %s",
        (session_id,)
    )
```

### 3. Session API 控制器

**文件**: `backend/api_controller/session_controller.py`

**修改前**:
```python
@router.delete("/{session_id}", response_model=Dict[str, Any], summary="删除会话")
async def delete_session(session_id: str):
    """删除会话（软删除）"""
    try:
        repo = get_session_repository()
        rows_affected = repo.delete_session(session_id)
        
        if rows_affected == 0:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        return {
            'success': True,
            'session_id': session_id,
            'message': '会话已删除'
        }
```

**修改后**:
```python
@router.delete("/{session_id}", response_model=Dict[str, Any], summary="删除会话")
async def delete_session(session_id: str):
    """删除会话（硬删除，不可恢复）同时删除关联的所有消息"""
    try:
        session_repo = get_session_repository()
        message_repo = get_message_repository()
        
        # 1. 先删除关联的消息
        messages_deleted = message_repo.delete_messages_by_session(session_id)
        logger.info(f"删除会话 {session_id} 的消息 {messages_deleted} 条")
        
        # 2. 删除会话
        rows_affected = session_repo.delete_session(session_id)
        
        if rows_affected == 0:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        return {
            'success': True,
            'session_id': session_id,
            'messages_deleted': messages_deleted,
            'message': f'会话已删除，同时删除了 {messages_deleted} 条消息'
        }
```

---

## 🔄 删除流程

```
用户点击删除会话
    ↓
DELETE /api/v1/session/{session_id}
    ↓
1. 删除消息表中的记录
   DELETE FROM message WHERE session_uuid = xxx
   ↓
   返回删除的消息数量
   
2. 删除会话表中的记录
   DELETE FROM session WHERE session_uuid = xxx
   ↓
   返回删除结果
   
3. 前端更新 UI
   - 从会话列表移除
   - 如果删除的是当前会话，清空消息区域
```

---

## 📋 响应格式

### 成功响应
```json
{
  "success": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "messages_deleted": 15,
  "message": "会话已删除，同时删除了 15 条消息"
}
```

### 失败响应（会话不存在）
```json
{
  "detail": "会话不存在"
}
```

---

## ⚠️ 注意事项

### 1. 数据不可恢复

硬删除后数据**永久丢失**，无法恢复。建议：
- 前端显示确认对话框
- 可以添加二次确认（重要操作）

### 2. 级联删除

删除会话时会自动删除关联的所有消息：
- ✅ 避免孤儿数据
- ✅ 保持数据一致性
- ✅ 节省存储空间

### 3. 数据库优化

如果数据量大，可以考虑：
```sql
-- 添加索引加速删除
CREATE INDEX idx_session_uuid ON message(session_uuid);
```

---

## 🧪 测试

### 1. 测试删除会话

```bash
# 创建会话
curl -X POST http://localhost:8000/api/v1/session/create \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001", "title": "测试删除"}'

# 发送消息
curl -X POST http://localhost:8000/api/v1/session/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001", "query": "测试", "session_id": "上一步返回的 session_id"}'

# 删除会话
curl -X DELETE http://localhost:8000/api/v1/session/{session_id}
```

### 2. 验证数据删除

```sql
-- 检查会话是否删除
SELECT * FROM session WHERE session_uuid = 'xxx';
-- 应该返回空

-- 检查消息是否删除
SELECT * FROM message WHERE session_uuid = 'xxx';
-- 应该返回空
```

---

## 📝 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `backend/database/mysql/repository/session_repository.py` | `delete_session()` 改为硬删除 |
| `backend/database/mysql/repository/message_repository.py` | 新增 `delete_messages_by_session()` |
| `backend/api_controller/session_controller.py` | 修改删除接口，实现级联删除 |

---

## ✅ 完成状态

- [x] SessionRepository 改为硬删除
- [x] MessageRepository 新增删除方法
- [x] API 控制器实现级联删除
- [x] 返回删除的消息数量
- [x] 添加日志记录
- [ ] 测试验证

---

删除会话已改为硬删除，同时会级联删除关联的所有消息！数据一旦删除将无法恢复。🔒
