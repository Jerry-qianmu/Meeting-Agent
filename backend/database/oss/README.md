# OSS 服务使用指南

## 概述

`OSSService` 提供阿里云对象存储服务，用于存储文档、图片和其他文件。

## 配置

在 `.env` 文件中添加以下配置：

```bash
# OSS 配置
OSS_ACCESS_KEY_ID=your_access_key_id
OSS_ACCESS_KEY_SECRET=your_access_key_secret
OSS_REGION=cn-hangzhou
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET=my-knowledge-agent
OSS_PREFIX=  # 可选，路径前缀
```

## 使用方法

### 1. 获取 OSS 服务实例

```python
from database.oss import get_oss_service

oss = get_oss_service()
```

### 2. 上传文件

#### 上传原始字节

```python
# 直接用完整 object_key 上传
object_key = "kb/my_kb_123/document.pdf"
file_content = b"..."  # 文件二进制内容

result = oss.upload_bytes(object_key, file_content)
# 返回：object_key
```

#### 按类目上传

```python
# 上传到指定类目
object_key = oss.upload_file(
    category="documents",
    file_name="report.pdf",
    file_content=file_content
)
# 返回：documents/report.pdf
```

#### 上传文档

```python
# 上传知识库文档
object_key = oss.upload_document(
    kb_id="kb_123",
    doc_id="doc_456",
    file_content=file_content,
    original_filename="report.pdf"
)
# 返回：documents/kb_123/doc_456/report.pdf
```

#### 上传处理后的文件

```python
# 上传中间文件（切片、元数据等）
object_key = oss.upload_processed_file(
    category="chunks",
    kb_id="kb_123",
    doc_id="doc_456",
    file_name="chunks.json",
    file_content=json.dumps(chunks).encode()
)
# 返回：chunks/kb_123/doc_456/chunks.json
```

### 3. 下载文件

#### 下载原始字节

```python
object_key = "kb/my_kb_123/document.pdf"
file_content = oss.get_object_bytes(object_key)
# 返回：bytes
```

#### 下载文档

```python
file_content = oss.get_document(
    kb_id="kb_123",
    doc_id="doc_456",
    original_filename="report.pdf"
)
```

### 4. 删除文件

#### 批量删除

```python
object_keys = [
    "kb/kb_123/doc_1.pdf",
    "kb/kb_123/doc_2.pdf",
]

deleted_count = oss.delete_objects(object_keys)
# 返回：成功删除的数量
```

#### 删除文档

```python
deleted_count = oss.delete_document(
    kb_id="kb_123",
    doc_id="doc_456"
)
# 删除文档的所有相关文件
```

#### 按前缀删除

```python
deleted_count = oss.delete_by_prefix("temp/")
# 删除所有以 temp/ 开头的文件
```

### 5. 生成预签名 URL

#### 下载 URL

```python
url = oss.get_presigned_url(
    object_key="kb/my_kb_123/document.pdf",
    expires=3600  # 1 小时
)
# 返回：临时下载 URL
```

#### 上传 URL

```python
upload_url = oss.get_presigned_url_for_upload(
    object_key="uploads/user_123/file.pdf",
    expires=3600
)
# 返回：临时上传 URL（PUT 方法）
```

#### 文档下载 URL

```python
url = oss.get_document_presigned_url(
    kb_id="kb_123",
    doc_id="doc_456",
    original_filename="report.pdf",
    expires=3600
)
```

### 6. 工具方法

#### 检查文件是否存在

```python
exists = oss.file_exists("kb/my_kb_123/document.pdf")
# 返回：bool
```

#### 获取文件大小

```python
size = oss.get_file_size("kb/my_kb_123/document.pdf")
# 返回：文件大小（字节）或 None
```

## 存储结构

```
bucket/
├── documents/              # 原始文档
│   ├── {kb_id}/
│   │   ├── {doc_id}/
│   │   │   ├── original.pdf
│   │   │   └── other_files
│   │   └── ...
│   └── ...
├── chunks/                 # 文档切片
│   ├── {kb_id}/
│   │   └── {doc_id}/
│   │       └── chunks.json
│   └── ...
├── metadata/               # 元数据
│   ├── {kb_id}/
│   │   └── {doc_id}/
│   │       └── metadata.json
│   └── ...
├── images/                 # 图片（如需要）
│   └── ...
└── exports/                # 导出文件
    └── ...
```

## 与 Repository 层的集成

```python
from database.mysql.repository import DocumentRepository
from database.oss import get_oss_service

# 初始化
oss = get_oss_service()
doc_repo = DocumentRepository(db_client)

# 上传文档并记录
def upload_and_record_document(kb_id, user_id, file_content, filename):
    # 1. 上传到 OSS
    object_key = oss.upload_document(
        kb_id=kb_id,
        doc_id="doc_uuid",
        file_content=file_content,
        original_filename=filename
    )
    
    # 2. 在数据库记录
    doc = doc_repo.create_document(
        kb_id=kb_id,
        user_id=user_id,
        original_filename=filename,
        file_extension=filename.split(".")[-1],
        file_size=len(file_content),
        oss_path=object_key,
        oss_bucket=oss.bucket
    )
    
    return doc
```

## 错误处理

所有方法在失败时都会抛出 `Exception`：

```python
try:
    oss.upload_bytes("path/to/file", content)
except Exception as e:
    logger.error(f"上传失败：{e}")
    # 处理错误
```

## 性能建议

1. **批量操作**：使用 `delete_objects` 批量删除，而不是逐个删除
2. **分片上传**：大文件（>100MB）考虑使用分片上传（需扩展实现）
3. **缓存**：频繁访问的文件可在应用层缓存
4. **URL 有效期**：根据使用场景设置合理的 `expires` 时间

## 注意事项

1. **安全性**：不要将 AccessKey 硬编码在代码中，使用环境变量
2. **权限控制**：确保 OSS Bucket 的权限设置正确（私有读取）
3. **成本**：关注 OSS 存储和流量费用
4. **备份**：重要文档建议多重备份
