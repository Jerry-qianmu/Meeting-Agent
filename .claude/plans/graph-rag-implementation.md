# 结构化图检索方案实现计划

## Context

当前项目使用 PyMuPDF 提取 PDF 纯文本 → 按字符数切 chunk → Embedding 入 Milvus → 向量+BM25 混合检索。
设计文档 `RAG方案对比与结构化图检索方案.md` 提出了基于文档结构建图的检索方案，需要用 MinerU HTTP API 做 PDF→MD 转换，用 Neo4j 存储图结构，实现图检索与现有向量检索的混合共存。

## 实现范围

### 新增文件（9 个）

| 文件 | 作用 |
|------|------|
| `backend/service/mineru_client.py` | MinerU HTTP API 客户端，PDF→Markdown |
| `backend/service/markdown_parser.py` | Markdown 结构解析器（标题层级、表格、引用） |
| `backend/service/graph_builder.py` | 从解析结果构建 DocumentGraph（节点+边） |
| `backend/service/ner_tool.py` | 轻量级 NER（正则规则，抽取人名/组织/技术等实体） |
| `backend/service/graph_retriever.py` | 图遍历检索引擎（结构检索/实体检索/混合检索） |
| `backend/service/query_router.py` | 查询意图分类，路由到 graph/vector/hybrid 模式 |
| `backend/database/neo4j/__init__.py` | 包初始化 |
| `backend/database/neo4j/neo4j_client.py` | Neo4j 连接管理（单例） |
| `backend/database/neo4j/neo4j_service.py` | Neo4j 图操作服务（节点/边 CRUD、图遍历查询） |

### 修改文件（6 个）

| 文件 | 修改内容 |
|------|----------|
| `backend/config/settings.py` | 添加 MinerU、Neo4j 配置项 |
| `backend/.env` | 添加 MinerU URL、Neo4j 连接信息 |
| `backend/service/parse.py` | 新增 `parse_markdown()` 函数，从 Markdown 按结构切 chunk |
| `backend/api_service/document_service.py` | 修改处理流程：PDF 走 MinerU→MD→图构建+传统 chunk 双轨 |
| `backend/service/retrieval_service.py` | 新增 `graph_search()`，修改 `search()` 支持 graph 策略 |
| `backend/requirements.txt` | 添加 `neo4j` 依赖 |

### 基础设施

| 文件 | 修改内容 |
|------|----------|
| `docker-compose.yml` | 添加 Neo4j 5 社区版服务 |

---

## 详细步骤

### Step 1: 基础设施 — Neo4j + 配置

**docker-compose.yml** — 添加 Neo4j 5 社区版：
```yaml
neo4j:
  image: neo4j:5-community
  ports:
    - "7474:7474"   # Web UI
    - "7687:7687"   # Bolt 协议
  environment:
    NEO4J_AUTH: neo4j/neo4j_password
  volumes:
    - neo4j_data:/data
```

**settings.py** — 新增配置项：
- `mineru_api_url` — MinerU 服务地址（默认 `http://localhost:8888`）
- `mineru_timeout` — 请求超时（默认 300s）
- `neo4j_uri` — Bolt 地址（默认 `bolt://localhost:7687`）
- `neo4j_user` / `neo4j_password`
- `graph_enabled` — 是否启用图检索（默认 True）
- `graph_max_depth` — 图遍历最大深度（默认 2）

**.env** — 添加对应环境变量。

---

### Step 2: MinerU 客户端

**`backend/service/mineru_client.py`**

```python
class MinerUClient:
    def __init__(self, api_url: str, timeout: int = 300):
        ...

    def parse_pdf(self, file_content: bytes, filename: str) -> str:
        """调用 MinerU HTTP API，返回 Markdown 文本"""
        # POST multipart/form-data 到 {api_url}/parse
        # 返回 markdown_content
```

关键点：
- 使用 `requests` 发送 multipart/form-data（file 字段）
- 超时处理、重试机制
- 单例模式 `get_mineru_client()`

---

### Step 3: Markdown 解析器

**`backend/service/markdown_parser.py`**

从设计文档的 `MarkdownParser` 类适配，核心功能：

```python
class MarkdownParser:
    def parse(self, markdown_text: str) -> dict:
        """返回 {sections, tables, references, raw_text}"""
```

- `_extract_sections()` — 按 `#` 标题提取层级结构（level, title, content）
- `_extract_tables()` — 提取 Markdown 表格（headers, rows）
- `_extract_references()` — 正则匹配 "详见3.2节"、"如表1所示" 等内部引用

---

### Step 4: NER 工具

**`backend/service/ner_tool.py`**

采用设计文档的 `SimpleRegexNER`，零依赖、毫秒级。同时增加英文模式适配学术论文场景。

---

### Step 5: 图构建器

**`backend/service/graph_builder.py`**

```python
class GraphBuilder:
    def build(self, doc_id: str, parsed: dict) -> DocumentGraph:
        # 1. 创建 Document 根节点
        # 2. 创建 Section 节点，建立 contains 层级边
        # 3. 创建 Table 节点
        # 4. 建立 next 顺序边（同级相邻章节）
        # 5. 建立 references 引用边
        # 6. NER 抽取实体，建立 mentions 边
```

---

### Step 6: Neo4j 客户端与服务

**`backend/database/neo4j/neo4j_client.py`**
- 使用 `neo4j` Python 驱动，单例模式

**`backend/database/neo4j/neo4j_service.py`**
- `create_document_graph()` — 将 DocumentGraph 写入 Neo4j
- `delete_document_graph()` — 删除文档的图数据
- `search_by_keyword()` — 关键词搜索节点
- `get_neighbors()` — 获取邻居节点
- `find_entity_mentions()` — 查找实体的所有提及位置
- `traverse_from_node()` — BFS 遍历返回子图

---

### Step 7: 图检索引擎

**`backend/service/graph_retriever.py`**

三种检索模式：
- `structure` — 关键词匹配 Section/Chunk → 图遍历扩展
- `entity` — 匹配 Entity → 反向查所有提及章节
- `hybrid` — 合并两种结果

---

### Step 8: 查询路由

**`backend/service/query_router.py`**

正则匹配路由：graph_structure / graph_entity / vector / hybrid

---

### Step 9: 修改 parse.py

新增 `parse_markdown()` 函数 — 按标题层级切分 Markdown 为 chunk，记录 section_title、breadcrumb。

---

### Step 10: 修改 document_service.py — 双轨处理

```
PDF 文件:
  1. MinerU HTTP API → Markdown 文本
  2. 存储 Markdown 到 OSS（备份）
  3. 轨道 A（传统）: parse_markdown() → chunks → MySQL + Milvus
  4. 轨道 B（图）: MarkdownParser → GraphBuilder → Neo4j
  5. 两轨并行，互不影响

MD/TXT 文件:
  直接走轨道 A + 轨道 B（跳过 MinerU）
```

---

### Step 11: 修改 retrieval_service.py

新增 `graph_search()` 和 `graph_enhanced_search()` 方法，修改 `search()` 支持 `graph_only` 和 `graph_hybrid` 策略。

---

### Step 12: 依赖更新

**requirements.txt** 添加 `neo4j>=5.0.0`

---

## 验证方式

1. 启动 Neo4j：`docker compose up -d neo4j`
2. 启动 MinerU 服务（已有）
3. 启动后端：`cd backend && uvicorn main:app`
4. 上传 PDF → 检查 MySQL + Milvus + Neo4j 三端数据
5. 查询测试：图检索 / 向量检索 / 混合检索三种模式
