# API 控制器修复说明

## 修复的文件

### 1. api_controller/knowledge_base_controller.py
完全重写，主要修复：
- 移除了错误的 `/api/v1` 前缀（使用 router 的 prefix 统一管理）
- 修正了依赖注入函数 `get_knowledge_base_service()`
- 添加了 `user_id` 参数支持（可从请求中传入或使用默认值）
- 优化了错误处理和日志记录
- 添加了 Pydantic 模型的 `from_attributes = True` 配置

### 2. api_controller/document_controller.py
完全重写，主要修复：
- 修正了依赖注入函数 `get_document_service()`
- 修复了文件上传逻辑（使用 `await file.read()`）
- 添加了 `user_id` 参数支持
- 优化了文档状态查询逻辑
- 修复了删除文档时的 cascade 操作
- 添加了 Pydantic 模型的 `from_attributes = True` 配置

## API 端点

### 知识库 API (prefix: /knowledge-base)

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | / | 创建知识库 |
| GET | / | 获取知识库列表 |
| GET | /{kb_id} | 获取知识库详情 |
| PUT | /{kb_id} | 更新知识库 |
| DELETE | /{kb_id} | 删除知识库 |
| GET | /{kb_id}/stats | 获取知识库统计 |
| POST | /search | 搜索知识库 |

### 文档 API (prefix: /document)

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /upload | 上传文档到知识库 |
| GET | / | 获取文档列表 |
| GET | /{doc_id} | 获取文档详情 |
| GET | /{doc_id}/status | 获取文档处理状态 |
| DELETE | /{doc_id} | 删除文档 |
| POST | /{doc_id}/retry | 重试处理失败的文档 |
| GET | /kb/{kb_id} | 获取知识库的文档列表 |

## 使用示例

### 1. 创建知识库

```bash
curl -X POST "http://localhost:8000/knowledge-base" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "我的知识库",
    "description": "测试知识库",
    "user_id": "user_001"
  }'
```

### 2. 上传文档

```bash
curl -X POST "http://localhost:8000/document/upload" \
  -F "kb_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "file=@/path/to/document.pdf" \
  -F "title=测试文档" \
  -F "user_id=user_001"
```

### 3. 获取文档状态

```bash
curl -X GET "http://localhost:8000/document/{doc_id}/status"
```

## 完整的路由注册

在 `main.py` 中：

```python
from api_controller import knowledge_base_router, document_router

app.include_router(knowledge_base_router, prefix="/api/v1")
app.include_router(document_router, prefix="/api/v1")
```

所以完整的 API 路径是：
- `/api/v1/knowledge-base`
- `/api/v1/document`

## 依赖说明

所有控制器都使用 FastAPI 的 `Depends` 进行依赖注入：

```python
def get_knowledge_base_service():
    db_client = get_db_client()
    return KnowledgeBaseService(db_client)
```

这样可以确保：
1. 每个请求都使用同一个 MySQL 客户端实例
2. 服务层可以正确访问数据库
3. 资源管理更加清晰
