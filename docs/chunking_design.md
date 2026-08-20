# Markdown 智能分块系统设计文档

> 最后更新：2026-07-14
> 版本：v2.0（三道防线 + 结构保持 + LLM 富化）

---

## 1. 系统概述

本系统负责将 Markdown 文档切分为适合 RAG 检索的 chunk（文档片段）。核心目标：

| 目标 | 说明 |
|---|---|
| **语义完整** | 利用 Markdown 标题层级自然切分，不破坏段落、代码块、表格的完整性 |
| **尺寸合理** | 每个 chunk 在 `[min_tokens, max_tokens]` 范围内，消除微小 chunk |
| **结构可追溯** | 每个 chunk 携带标题面包屑，合并时保留父子层级关系 |
| **富化可检索** | LLM 为每个 chunk 生成 description + keywords，支持语义检索 |

### 参考的开源项目

| 项目 | Stars | 借鉴的设计 |
|---|---|---|
| [Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured) | ~15,000 | 表格按行拆分 + 每个续块重复表头；累加器模式的最小尺寸保障 |
| [yzp0111/structchunk](https://github.com/yzp0111/structchunk) | 2 | 标题面包屑注入；`merge_tiny` 后处理模式 |
| [zirkelc/chunkdown](https://github.com/zirkelc/chunkdown) | 61 | 父节点优先与子节点合并；按节点类型配置拆分规则 |
| [chonkie-inc/chonkie](https://github.com/chonkie-inc/chonkie) | ~4,400 | 前向贪心合并；`min_chars` 防止源头产生小 split |
| [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | ~100,000 | `MarkdownHeaderTextSplitter` 的标题栈解析模式 |

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    DocumentService                           │
│  _parse_markdown(doc_id, file_content)                      │
│                                                             │
│  ① chunk_markdown(content)    ← 同步，返回最终 chunks        │
│  ② ChunkGraph.build()         ← 同步，构建结构图             │
│  ③ _enrich_chunks_async()     ← 后台线程，LLM 富化 + 回写    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               MarkdownHierarchicalChunker                    │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│  │ 解析标题树 │→ │ 自底向上  │→ │ 后处理扫描│→ │ 分配ID    │ │
│  │ _parse_   │   │ _emit_   │   │ _absorb_ │   │ uuid4()  │ │
│  │ section_  │   │ chunks() │   │ small_   │   │          │ │
│  │ tree()    │   │          │   │ chunks() │   │          │ │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘ │
│       │              │               │                      │
│       ▼              ▼               ▼                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                │
│  │ 解析内容块 │   │ _split_  │   │ 结构保持  │                │
│  │ _parse_   │   │ and_     │   │ 标题标记  │                │
│  │ blocks()  │   │ emit()   │   │ 注入     │                │
│  └──────────┘   └──────────┘   └──────────┘                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  ChunkEnricher              ChunkGraph                      │
│  ┌─────────────────┐        ┌─────────────────┐            │
│  │ LLM 生成         │        │ 父子/兄弟关系    │            │
│  │ description +    │        │ 上下文窗口       │            │
│  │ keywords         │        │ 结构元数据       │            │
│  └─────────────────┘        └─────────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 核心算法详解

### 3.1 阶段一：解析标题树

**函数**: `_parse_section_tree(markdown_text) → SectionNode`

将 Markdown 按 `#` ~ `######` 标题解析为树结构：

```markdown
# Chapter 1                    → SectionNode(level=1, title="Chapter 1")
  content of chapter 1          → blocks: [paragraph]
  ## Section 1.1                → SectionNode(level=2, title="Section 1.1")
    content of section 1.1      → blocks: [paragraph, table]
  ## Section 1.2                → SectionNode(level=2, title="Section 1.2")
    content of section 1.2      → blocks: [paragraph]
# Chapter 2                    → SectionNode(level=1, title="Chapter 2")
  content of chapter 2          → blocks: [paragraph]
```

**树结构**:
```
root (level=0)
├── # Chapter 1 (level=1)
│   ├── blocks: [paragraph]
│   ├── ## Section 1.1 (level=2)
│   │   └── blocks: [paragraph, table]
│   └── ## Section 1.2 (level=2)
│       └── blocks: [paragraph]
└── # Chapter 2 (level=1)
    └── blocks: [paragraph]
```

**关键设计**: 每个节点只存储自己的直属 blocks，不包含子节点的内容。这保证了自底向上合并时的灵活性。

### 3.2 阶段二：解析内容块

**函数**: `_parse_blocks(text) → List[ContentBlock]`

将每个 section 的直属文本解析为 5 种原子单元：

| 类型 | 识别规则 | 是否可拆分 |
|---|---|---|
| `paragraph` | 普通文本段落 | 可拆（但作为最小单元不拆） |
| `code` | ` ``` ` 或 `~~~` 围栏代码块 | 不可拆（原子单元） |
| `table` | `\|` 开头的行，排除分隔行 | 可按行拆分（见 3.5） |
| `list` | `- ` / `* ` / `1. ` 开头 | 不可拆（原子单元） |
| `blank` | 空行（跳过，不计入 blocks） | — |

**表格解析改进**（v2.0）:
```python
TABLE_ROW_RE = re.compile(r'^\|.+\|')           # 行首有 | 即可
TABLE_SEPARATOR_RE = re.compile(r'^\|?\s*[-:]+[-| :]*$')  # 匹配 |---|---|
```
- 跳过独立的分隔行，只在数据行开始时触发表格解析
- 表格内包含分隔行（`|---|---|`）作为表头标识

### 3.3 阶段三：自底向上分块

**函数**: `_emit_chunks(node, chunks)`

处理顺序：**先处理所有子节点，再处理当前节点**（后序遍历）。

```
处理顺序：
  Section 1.1 → Section 1.2 → Chapter 1 → Chapter 2
```

**决策逻辑**:

```
if 直属内容 tokens == 0:
    跳过（该节点只有子节点，无直属内容）

elif 直属内容 tokens <= max_overflow (1200):
    if 直属内容 tokens < min_tokens (100) 且已有 chunk:
        → _merge_or_emit（尝试合并到前一个 chunk）
    else:
        → _emit_as_chunk（正常 emit）

else:  # 直属内容超过 max_overflow
    → _split_and_emit（拆分后 emit）
```

### 3.4 三道防线：消除微小 chunk

#### 防线 1：`_split_and_emit` 内部即时检查

**问题**: 拆分大 section 时，循环中间 emit 的 chunk 不检查 min_tokens。

**解决**: 每次 emit 后立即检查，如果是小 chunk 则合并回前一个。

```python
# _split_and_emit 循环中
self._emit_as_chunk(current_blocks, ...)
if (len(chunks) >= 2 and chunks[-1].token_count < self.min_tokens
        and self._try_merge_to_prev(chunks[:-1], heading_path)):
    prev = chunks[-2]
    small = chunks[-1]
    prev.content += '\n\n' + small.content
    prev.token_count += small.token_count
    chunks.pop()
```

#### 防线 2：`_merge_or_emit` 跨 section 合并

**问题**: 自底向上处理时，第一个子节点没有前置 chunk 可合并；不同 heading_path 的相邻 section 无法合并。

**解决**:

```python
def _merge_or_emit(self, blocks, heading_path, level, chunks):
    if not chunks:
        # 第一个 chunk 无前置 → 直接 emit（由防线3兜底）
        self._emit_as_chunk(blocks, heading_path, level, chunks)
        return

    last = chunks[-1]

    # 策略1：同 section 直接合并（无需标题标记）
    if last.heading_path == heading_path:
        last.content += '\n\n' + body
        return

    # 策略2：父子 section 关系，注入标题标记后合并
    if is_ancestor(last.heading_path, heading_path) or is_ancestor(heading_path, last.heading_path):
        if last.token_count + current_tokens <= max_overflow:
            heading_marker = heading_path[-1]  # "## Section Title"
            last.content += '\n\n' + heading_marker + '\n\n' + body
            return

    # 无法合并 → 正常 emit
    self._emit_as_chunk(blocks, heading_path, level, chunks)
```

#### 防线 3：`_absorb_small_chunks` 后处理扫描

**问题**: 防线 1 和 2 仍有遗漏（第一个 chunk、max_overflow 阻止合并等）。

**解决**: 所有 chunk 生成后，遍历一遍，吸收所有剩余小 chunk。

```python
def _absorb_small_chunks(self, chunks):
    relaxed_max = self.max_tokens * 2  # 放宽上限用于吸收小 chunk
    i = 1
    while i < len(chunks):
        if chunks[i].token_count < self.min_tokens:
            # 策略1：向前合并到前一个 chunk
            if prev.token_count + curr.token_count <= relaxed_max:
                # 跨 section 时注入标题标记
                if prev.heading_path != curr.heading_path:
                    prev.content += '\n\n' + heading_text + '\n\n' + curr.content
                else:
                    prev.content += '\n\n' + curr.content
                chunks.pop(i)
                continue

            # 策略2：向后合并到后一个 chunk
            if curr.token_count + nxt.token_count <= relaxed_max:
                nxt.content = curr.content + '\n\n' + nxt.content
                chunks.pop(i)
                continue

        i += 1
    return chunks
```

**合并上限说明**:

| 场景 | 上限 | 理由 |
|---|---|---|
| 正常拆分 | `max_tokens` (800) | 目标尺寸 |
| 原子单元溢出 | `max_overflow` (1200) | 保护代码块/表格不被拆断 |
| 小 chunk 吸收 | `relaxed_max` (1600) | 优先消除小 chunk，允许适度溢出 |

### 3.5 表格按行拆分

**函数**: `_split_table_block(table_block) → List[ContentBlock]`

**借鉴来源**: Unstructured 的 `_HtmlTableSplitter`

当表格 token 超过 `max_tokens` 时，按数据行拆分，每个子表格重复表头：

```
原始表格（2000 tokens）:
  | Name | Age | City |
  |------|-----|------|
  | Alice | 30 | NYC |
  | Bob | 25 | LA |
  | ... (很多行) |

拆分后:
  子表格1 (400 tokens):
    | Name | Age | City |
    |------|-----|------|
    | Alice | 30 | NYC |
    | Bob | 25 | LA |

  子表格2 (400 tokens):
    | Name | Age | City |
    |------|-----|------|
    | Charlie | 35 | SF |
    | ... |
```

**算法**:
1. 识别表头行 + 分隔行（`|---|---|`）
2. 数据行逐行累加 token
3. 超过 `max_tokens` 时，当前组生成子表格（header + 数据行）
4. 开始下一组，重新计入 header_tokens

### 3.6 标题面包屑注入

**借鉴来源**: structchunk 的每个 chunk 携带 header breadcrumbs

在 `_emit_as_chunk` 中，为每个 chunk 内容前注入 HTML 注释格式的面包屑：

```html
<!-- # Chapter 1 > ## Section 1.1 > ### Subsection 1.1.1 -->

实际 chunk 内容...
```

**设计选择**:
- 使用 HTML 注释 `<!-- -->` 格式，不干扰 Markdown 渲染
- 面包屑用 ` > ` 分隔，清晰展示层级
- 通过 `prepend_heading_path` 参数控制开关（默认开启）

**对面包屑的影响**:
- 面包屑会增加 token 数（深层级约 20-40 tokens）
- `min_tokens` 判断使用原始 block tokens，emit 后重新计算包含面包屑的 token

---

## 4. Chunk 富化系统

### 4.1 ChunkEnricher

**文件**: `chunk_enricher.py`

为每个 chunk 调用 LLM 生成 description（摘要）和 keywords（关键词）。

**调用方式**: 并行调用（`ThreadPoolExecutor`, max_workers=10）

**Prompt 设计要点**:
- 输入包含 **标题路径**，LLM 能感知层级关系
- 要求 description 体现父子关系（如"在X主题下，分别介绍了Y和Z"）
- 要求 keywords 包含标题路径中的关键主题词
- 内容超过 3000 字符时截断

**输出格式**:
```json
{
  "description": "在Redis持久化机制中，RDB和AOF是两种核心方案...",
  "keywords": ["Redis", "RDB", "AOF", "持久化", "快照"]
}
```

### 4.2 数据一致性保障

**问题**: enrichment 在后台线程执行，MySQL 写入在 enrichment 完成之前。

**解决**: enrichment 完成后回写 MySQL。

```
时序：
  ① 分块 → chunks
  ② 写 MySQL (description=null) → 记录 db_chunk_id
  ③ 写 Milvus (原文向量)
  ④ 后台线程: LLM 富化 → 回写 MySQL (description=实际值) → 写 Milvus description collection
```

**回写逻辑** (`_enrich_chunks_async`):
```python
# 1. 回写 MySQL
mysql_updates = [{'chunk_id': c['db_chunk_id'], 'description': ..., 'keywords': ...} ...]
chunk_repo.update_description_batch(mysql_updates)

# 2. 更新 Milvus description collection
milvus.upsert_descriptions(collection_name, descriptions)
```

### 4.3 ChunkGraph 结构图

**文件**: `chunk_graph.py`

基于 heading_path 构建 chunk 间的结构关系：

| 关系 | 说明 | 用途 |
|---|---|---|
| `parent_index` | 父节点 chunk 索引 | 检索时补充上下文 |
| `children_indices` | 子节点 chunk 索引列表 | 展开主题详情 |
| `sibling_indices` | 兄弟节点 chunk 索引列表 | 获取相关内容 |

**上下文窗口** (`get_context_window`):
```python
# 检索到 chunk[i] 时，自动补充：
context = [chunk[i], chunk[parent], chunk[sibling_1], chunk[sibling_2]]
```

---

## 5. 数据结构

### 5.1 ContentBlock（内部使用）

```python
@dataclass
class ContentBlock:
    block_type: str       # 'paragraph', 'code', 'table', 'list'
    content: str          # 原始文本
    token_count: int      # token 估算
    line_start: int       # 起始行号
    line_end: int         # 结束行号
```

### 5.2 SectionNode（内部使用）

```python
@dataclass
class SectionNode:
    level: int                # 标题层级 (1-6, 0=根节点)
    title: str                # 标题文本
    heading_path: List[str]   # ["# Ch1", "## Sec1.1", "### Sub1.1.1"]
    blocks: List[ContentBlock]    # 直属内容块
    children: List[SectionNode]   # 子节点
    total_tokens: int         # 子树总 token
```

### 5.3 ChunkResult（输出）

```python
@dataclass
class ChunkResult:
    chunk_id: str             # UUID
    content: str              # 最终内容（含面包屑）
    heading_path: List[str]   # 标题路径
    heading_level: int        # 标题层级
    token_count: int          # token 数（含面包屑）
    start_line: int           # 起始行号
    end_line: int             # 结束行号
    block_count: int          # 包含的 block 数
    metadata: Dict[str, Any]  # chunk_index, parent_index 等
```

### 5.4 输出字典格式

`chunk_markdown()` 返回的字典列表：

```python
{
    'chunk_id': 'uuid',
    'content': '<!-- # Ch1 > ## Sec1.1 -->\n\n实际内容...',
    'heading_path': ['# Ch1', '## Sec1.1'],
    'heading_level': 2,
    'token_count': 250,
    'start_char': 0,
    'end_char': 500,
    'chunk_order': 0,
    'metadata': {
        'heading_path': ['# Ch1', '## Sec1.1'],
        'heading_level': 2,
        'block_count': 3,
        'start_line': 10,
        'end_line': 25,
        'parent_index': None,
        'children_indices': [1, 2],
        'sibling_indices': [],
    },
    'description': '在Chapter 1中，Section 1.1介绍了...',  # enrichment 后填充
    'keywords': ['关键词1', '关键词2'],                      # enrichment 后填充
}
```

---

## 6. 配置参数

| 参数 | 环境变量 | 默认值 | 说明 |
|---|---|---|---|
| `min_tokens` | `MD_CHUNK_MIN_TOKENS` | 100 | chunk 最小 token（过小则合并） |
| `max_tokens` | `MD_CHUNK_MAX_TOKENS` | 800 | chunk 最大 token（过大则拆分） |
| `max_overflow_ratio` | 硬编码 1.5 | 1.5 | 原子单元溢出比例（max_tokens × 1.5 = 1200） |
| `prepend_heading_path` | `MD_CHUNK_PREPEND_HEADING` | true | 是否注入标题面包屑 |
| `md_enrich_model` | `MD_ENRICH_MODEL` | deepseek-v4-pro | 富化用 LLM 模型 |
| 富化并发数 | 硬编码 | 10 | ThreadPoolExecutor workers |

---

## 7. 文件结构

```
backend/service/chunking/
├── __init__.py              # 导出 MarkdownHierarchicalChunker, chunk_markdown, ChunkEnricher, ChunkGraph
├── md_chunker.py            # 核心分块器（解析 + 分块 + 三道防线）
├── chunk_enricher.py        # LLM 富化（description + keywords）
└── chunk_graph.py           # 结构图（父子/兄弟关系 + 上下文窗口）

backend/config/settings.py           # 配置参数
backend/api_service/document_service.py  # 调用入口
backend/database/mysql/repository/chunk_repository.py  # MySQL 持久化
```

---

## 8. 算法复杂度与性能

| 阶段 | 时间复杂度 | 说明 |
|---|---|---|
| 标题树解析 | O(n) | n = 文档行数 |
| 内容块解析 | O(n) | 每行只访问一次 |
| 自底向上分块 | O(m) | m = section 节点数 |
| 后处理扫描 | O(c) | c = chunk 数 |
| 结构图构建 | O(c²) | 父子关系需要两两比较 |
| LLM 富化 | O(c / workers) | 并行调用，受 API 速率限制 |

**实际表现**（参考值）:
- 13,000 字文档 → ~30-50 个 chunk → 富化约 30-60 秒（10 workers）
- 分块本身 < 1 秒

---

## 9. 已知限制与后续改进

| 限制 | 说明 | 可能的改进方向 |
|---|---|---|
| 长代码块无法拆分 | 超大代码块整体 emit | 按函数/类边界拆分（检测空行+缩进） |
| 长列表无法拆分 | 超大列表整体 emit | 按列表项边界拆分 |
| 无 chunk 重叠 | 相邻 chunk 无上下文重叠 | 前一个 chunk 的最后 N 个 token 作为 overlap |
| YAML Frontmatter | 被解析为普通段落 | 识别 `---...---` 块作为独立 metadata |
| 水平分割线 | `---` 未作为分块边界 | 识别为独立 block 类型，视为分块边界 |
| 结构图 O(c²) | chunk 数多时构建慢 | 改用排序 + 栈的 O(c log c) 算法 |
