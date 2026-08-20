# 智能分块策略设计讨论

> 日期：2026-07-12
> 背景：面试问答 Agent 的 RAG 系统 chunk 策略重构

---

## 一、当前设计思路

### 核心理念

传入的文档全部采用 md 格式，利用 md 天然的层级结构进行语义分块，而非固定窗口切分。

### 处理流程

```
文档 (md)
  │
  ├─ 按 md 标题层级自然分段
  │   ├─ 段落A (token合理) → chunk + description + keywords
  │   ├─ 段落B (token合理) → chunk + description(携带A的description) + keywords
  │   └─ 段落C (token过大) → 递归拆分子标题
  │
  ├─ 构建图：标题层级 + description 关联
  │
  └─ 检索时：先搜 description → 图上循迹 → 取完整 chunk
```

### 设计要点

1. **按 md 层级结构分块**：不按固定 token 数切分，而是尊重 md 的标题层级，每个标题下的内容作为候选 chunk
2. **token 估算**：使用 embedding 模型对应的 tokenizer 估算 token 数量
3. **description 生成**：调用 LLM 为每个 chunk 生成 description，同时提取 keywords（包含 Fig1、表2 等标识性词语）
4. **description 串联**：同一层级的下一个 chunk 生成 description 时，携带上一个 chunk 的 description 信息
5. **图构建**：根据标题结构和 chunk 的 description 构建图
6. **检索优化**：先检索 description 快速判断 chunk 是否需要，再在图上循迹防止孤立 chunk 信息不足

---

## 二、逐点分析

### 2.1 按 md 层级结构分块

**优势**：语义完整性远好于固定窗口。一个 `## Redis持久化` 下面的内容天然是一体的。

**边界 case 需要处理**：

| 场景 | 问题 | 建议方案 |
|---|---|---|
| 段落 token 过大 | 一个 `##` 下有 3000 token，超出合理范围 | 递归到 `###` 子标题拆分；若无子标题，按段落/语义边界 fallback 切分 |
| 段落 token 过小 | 一个 `###` 只有 30 token，单独成 chunk 太碎片 | 向上合并：与同级相邻段落合并，或与父级合并 |
| 表格/代码块跨标题 | 代码块可能属于前一个标题也可能独立存在 | 需要明确归属规则（建议归属于前一个标题） |

### 2.2 每个 chunk 生成 description + keywords

**价值**：检索时先匹配 description（几十 token）而不是全文（几百 token），用索引换推理成本。

**需要考虑的问题**：

- **LLM 调用成本**：一篇 50 个 chunk 的文档需要 50 次 LLM 调用。文档量大时预处理成本不可忽略。建议用轻量模型（如 `qwen3.5-plus`）而非 `deepseek-v4-pro`。
- **description 质量依赖 prompt**：需要精确的 prompt，要求输出：
  - 一句话描述核心内容
  - 关键术语 + 标识性词语（Fig1、表2、算法3 等）
  - 和上下文的关系（承接上文什么、引出下文什么）

### 2.3 携带上一个 description

**意图**：让 description 之间有连贯性，对检索有帮助。

**风险**：如果上一个 description 质量不好（模型生成错误），错误会**级联传播**到后续所有 description。

**建议**：在 prompt 中明确告诉模型"参考上文摘要，但以上文摘要仅供参考，以当前内容为准"。

### 2.4 构建图

图有两种边：

**结构边（标题层级）**：
```
# 面试八股文
  ├── ## Redis
  │     ├── ### 持久化
  │     ├── ### 缓存淘汰
  │     └── ### 分布式锁
  └── ## MySQL
        ├── ### 索引
        └── ### 事务
```

**语义边（description 关联）**：
```
chunk_持久化  ──"相关内容"──>  chunk_MySQL事务   (都涉及数据一致性)
chunk_分布式锁 ──"对比"──>     chunk_Redisson    (实现方案对比)
```

**问题**：

- **语义边怎么构建？** 入库时对所有 chunk 的 description 做全局相似度计算（O(n²) embedding），或让 LLM 判断关联关系（O(n²) LLM 调用）。需要可扩展方案。
- **图上循迹的检索策略？** 走几步？走哪条边？需要明确图遍历规则。
- **孤立 chunk 怎么处理？** 有些 chunk 确实是独立的，不要为了连通而强行建边。

### 2.5 检索时先搜 description

**核心假设**：description 能准确代表 chunk 内容。但这个假设不一定成立：

- **description 可能遗漏关键信息**：chunk 详细讲了"RDB 和 AOF 的区别"，description 可能只写"Redis 持久化机制概述"
- **embedding 空间偏移**：description 是 LLM 的"摘要语言"，chunk 原文是"技术语言"，在 embedding 空间可能有偏移

**建议**：description 检索作为第一轮粗筛，最终精排仍基于 chunk 原文（利用现有 reranker）。

---

## 三、建议补充的关键设计

### 3.1 Chunk 的 metadata 结构

```python
@dataclass
class SmartChunk:
    chunk_id: str
    doc_id: str
    content: str              # 原文
    description: str          # LLM 生成的描述
    keywords: List[str]       # 关键词 + 标识性词语

    # 标题层级
    heading_path: List[str]   # ["# 面试八股文", "## Redis", "### 持久化"]
    heading_level: int        # 3

    # 图相关
    parent_id: Optional[str]  # 父 chunk
    children_ids: List[str]   # 子 chunk
    sibling_ids: List[str]    # 同级 chunk
    related_ids: List[str]    # 语义关联 chunk

    # token 信息
    token_count: int
    description_tokens: int
```

### 3.2 两阶段检索策略

```
用户 query
    │
    ▼
阶段 1：粗筛（description + keywords）
    - 用 query 对所有 description 做向量检索 → top_k 个候选
    - 用 keywords 做精确匹配补充 → 补充命中
    - 合并去重
    │
    ▼
阶段 2：图扩展
    - 对每个候选 chunk，沿图走 1-2 步取邻居
    - 邻居作为上下文补充（不是独立结果）
    │
    ▼
阶段 3：精排（原文 rerank）
    - 用 query 对候选 chunk 的原文做 rerank
    - 最终 top_k 作为上下文
```

### 3.3 Description 生成的增量更新

文档更新时（比如中间插入一个新 chunk），后续所有 chunk 的 description 都需要重新生成。需要**增量更新策略**：只重新生成受影响的 chunk 的 description，而不是全量重算。

---

## 四、总结评价

| 设计点 | 评价 | 风险 |
|---|---|---|
| md 层级分块 | ✅ 正确方向 | 需要处理过大/过小段落的边界 case |
| description + keywords | ✅ 核心创新 | LLM 调用成本高，description 质量依赖 prompt |
| 携带上一个 description | ⚠️ 有价值但有风险 | 错误会级联传播，建议加"仅供参考"约束 |
| 构建图 | ⚠️ 创新点但复杂度高 | 需要明确图的构建方式和遍历策略 |
| 先搜 description | ✅ 核心收益 | description 和原文 embedding 空间可能有偏移 |

---

## 五、建议实施优先级

1. **P0 - 先把 md 层级分块 + description 生成跑通**，验证 description 检索的效果
2. **P1 - 图的部分先用简单的标题层级树**（结构边），语义边后面再加
3. **P2 - 检索策略先做 description 粗筛 + 原文 rerank**，图遍历作为后续优化

---

## 六、待讨论问题

- [ ] chunk 的 token 合理范围设定（min/max）
- [ ] 无子标题时的 fallback 切分策略
- [ ] description 生成的 prompt 设计
- [ ] 小 chunk 的向上合并策略
- [ ] 语义边的构建方案（embedding vs LLM）
- [ ] 图遍历的具体策略（步数、方向、权重）
- [ ] description 检索与原文 rerank 的衔接方式
