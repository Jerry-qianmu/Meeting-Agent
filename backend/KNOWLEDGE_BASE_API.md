# Knowledge Base API 实现文档

## 项目概述

实现了完整的知识库和文档管理系统，支持：
1. 创建知识库
2. 上传 PDF 文档到 OSS
3. 在 MySQL 中记录文档信息
4. 文档分块（chunking）
5. 向量化并上传到 Milvus

## 项目结构

```
backend/
├── main.py                          # FastAPI 应用入口
├── api_service/                     # 业务服务层
│   ├── __init__.py
│   ├── config.py                    # 配置管理
│   ├── knowledge_base_service.py    # 知识库服务
│   └── document_service.py          # 文档处理服务
├── api_controller/                  # API 控制器层
│   ├── __init__.py
│   ├── knowledge_base_controller.py # 知识库 API
│   └── document_controller.py       # 文档 API
└── database/
    ├── mysql/                       # MySQL 数据库层（已存在）
    ├── milvus/                      # Milvus 向量数据库（已存在）
    └── oss/                         # OSS 文件存储（已存在）
```

## API 端点

### 知识库管理

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/knowledge-base` | 创建知识库 |
| GET | `/api/v1/knowledge-base` | 获取知识库列表 |
| GET | `/api/v1/knowledge-base/{kb_id}` | 获取知识库详情 |
| PUT | `/api/v1/knowledge-base/{kb_id}` | 更新知识库 |
| DELETE | `/api/v1/knowledge-base/{kb_id}` | 删除知识库 |
| GET | `/api/v1/knowledge-base/{kb_id}/stats` | 获取知识库统计 |
| POST | `/api/v1/knowledge-base/search` | 搜索知识库 |

### 文档管理

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/document/upload` | 上传文档到知识库 |
| GET | `/api/v1/document` | 获取文档列表 |
| GET | `/api/v1/document/{doc_id}` | 获取文档详情 |
| GET | `/api/v1/document/{doc_id}/status` | 获取文档处理状态 |
| DELETE | `/api/v1/document/{doc_id}` | 删除文档 |
| POST | `/api/v1/document/{doc_id}/retry` | 重试处理失败的文档 |
| GET | `/api/v1/document/kb/{kb_id}` | 获取知识库的文档列表 |

## 使用示例

### 1. 创建知识库

```bash
curl -X POST "http://localhost:8000/api/v1/knowledge-base" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "我的知识库",
    "description": "这是一个测试知识库",
    "embedding_model": "text-embedding-v4",
    "embedding_dimension": 768
  }'
```

响应：
```json
{
  "kb_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user_001",
  "name": "我的知识库",
  "description": "这是一个测试知识库",
  "collection_name": "kb_user001_我的知识库_a1b2c3d4",
  "doc_count": 0,
  "chunk_count": 0,
  "total_tokens": 0,
  "embedding_model": "text-embedding-v4",
  "status": 1,
  "is_private": true,
  "created_at": "2026-05-01 18:00:00",
  "updated_at": "2026-05-01 18:00:00"
}
```

### 2. 上传 PDF 文档

```bash
curl -X POST "http://localhost:8000/api/v1/document/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "kb_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "file=@/path/to/document.pdf" \
  -F "title=测试文档"
```

响应：
```json
{
  "doc_uuid": "660e8400-e29b-41d4-a716-446655440001",
  "kb_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user_001",
  "title": "测试文档",
  "original_filename": "document.pdf",
  "file_extension": "pdf",
  "file_size": 102400,
  "oss_path": "documents/550e8400-e29b-41d4-a716-446655440000/document.pdf",
  "oss_bucket": "rag-system-test",
  "chunk_count": 0,
  "total_tokens": 0,
  "status": 1,
  "version": 1,
  "metadata": null,
  "created_at": "2026-05-01 18:05:00",
  "updated_at": "2026-05-01 18:05:00"
}
```

### 3. 检查文档处理状态

```bash
curl -X GET "http://localhost:8000/api/v1/document/660e8400-e29b-41d4-a716-446655440001/status"
```

响应：
```json
{
  "doc_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": 2,
  "status_text": "done",
  "processed_chunks": 15,
  "total_chunks": 15,
  "progress_percent": 100.0
}
```

## 数据流程

### 文档上传和处理流程

```
用户上传 PDF
    ↓
1. 验证文件格式和大小
    ↓
2. 上传到 OSS
    ↓
3. 在 MySQL 创建文档记录（status=0, pending）
    ↓
4. 标记为处理中（status=1, processing）
    ↓
5. 解析 PDF 内容（使用 pdfplumber）
    ↓
6. 文档分块（chunk_size=500, chunk_overlap=50）
    ↓
7. 保存 chunk 到 MySQL 表
    ↓
8. 向量化（使用 DashScope text-embedding-v4）
    ↓
9. 上传到 Milvus collection
    ↓
10. 更新文档状态（status=2, done）
    ↓
11. 更新知识库统计信息（doc_count, chunk_count, total_tokens）
```

## 技术要点

### 1. UUID 格式

所有 ID 统一使用 CHAR(36) 字符串格式：
```python
kb_id = str(uuid.uuid4())  # 例如："550e8400-e29b-41d4-a716-446655440000"
```

### 2. 文档状态

- `0` - pending: 待处理
- `1` - processing: 处理中
- `2` - done: 处理完成
- `3` - failed: 处理失败

### 3. 分块策略

- 块大小：500 字符
- 重叠大小：50 字符
- Token 估算：中文字符≈1.5 tokens，英文字符≈0.25 tokens

### 4. Milvus Collection 设计

每个知识库对应一个 Milvus collection，包含：
- `chunk_id`: 切片唯一 ID（主键）
- `doc_id`: 文档 ID
- `job_id`: 任务 ID
- `chunk_index`: 切片顺序
- `content`: 切片内容
- `dense`: 向量数据（768 维）
- `sparse_bm25`: BM25 稀疏向量
- 元数据字段：kb_id, doc_id, chunk_order

### 5. 异步处理

文档处理设计为异步模式：
- API 立即返回文档信息
- 后台线程处理 PDF 解析、分块、向量化
- 可通过 `/api/v1/document/{doc_id}/status` 查询处理进度

## 启动应用

```bash
cd /mnt/d/Study/Agents/MA/data3/zb/MyAgent/backend
python main.py
```

或使用 uvicorn：

```bash
cd /mnt/d/Study/Agents/MA/data3/zb/MyAgent/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

访问 API 文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 依赖安装

```bash
pip install fastapi uvicorn python-multipart pydantic pydantic-settings
pip install pymysql mysql-connector-python
pip install pymilvus
pip install alibabacloud_oss_v2
pip install dashscope
pip install pdfplumber
```

## 注意事项

1. **用户 ID**: 当前使用硬编码的 `user_001`，实际使用时需要从 JWT token 中获取
2. **文件大小限制**: 默认 50MB，可在 `document_service.py` 中修改
3. **支持格式**: 目前支持 PDF、TXT、MD，可扩展到 DOCX 等格式
4. **错误处理**: 所有 API 都有完整的错误处理和日志记录
5. **CORS**: 已配置允许所有来源，生产环境应限制

## 后续优化

1. 添加用户认证和授权
2. 支持更多文档格式（DOCX、PPTX、Excel 等）
3. 实现更智能的分块策略（按章节、段落等）
4. 添加文档版本管理
5. 实现文档搜索和检索 API
6. 添加批量上传功能
7. 实现处理队列和任务调度
8. 添加监控和告警
