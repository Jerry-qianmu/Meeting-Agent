# Markdown Parser - 基于图RAG的Markdown解析系统

## 简介

这是一个基于图RAG思想的Markdown解析系统，能够：

1. **清理文本** - 自动识别并移除页眉页脚、噪声等无用信息
2. **解析结构** - 按Markdown标题层级解析文档结构
3. **提取实体** - 使用NER模型提取命名实体（人名、组织、时间等）
4. **智能分块** - 基于token数量的智能分块策略
5. **构建图结构** - 构建包含Document、Section、Chunk、Entity的图结构

## 安装依赖

```bash
pip install transformers torch tiktoken networkx matplotlib
```

## 目录结构

```
markdown_parser/
├── __init__.py          # 包初始化
├── config.py            # 配置文件
├── main.py              # 主入口
├── visualize.py         # 可视化脚本
├── README.md            # 说明文档
├── cleaners/
│   ├── __init__.py
│   └── text_cleaner.py  # 文本清理器
├── parsers/
│   ├── __init__.py
│   └── markdown_parser.py  # Markdown解析器
├── ner/
│   ├── __init__.py
│   └── entity_extractor.py  # 实体提取器
├── chunkers/
│   ├── __init__.py
│   └── chunk_splitter.py  # Chunk分割器
├── graph/
│   ├── __init__.py
│   └── graph_builder.py  # 图结构构建器
└── utils/
    ├── __init__.py
    └── token_counter.py  # Token计数器
```

## 使用方法

### 命令行使用

```bash
# 处理单个文件
python -m markdown_parser.main input.md -o output/

# 详细输出
python -m markdown_parser.main input.md -o output/ -v
```

### Python代码使用

```python
from markdown_parser import MarkdownProcessor

# 创建处理器
processor = MarkdownProcessor()

# 处理文件
result = processor.process_file("input.md")

# 打印摘要
processor.print_summary(result)

# 保存结果
processor.save_result(result, "output/")
```

### 可视化

```bash
# 从JSON文件生成图
python -m markdown_parser.visualize output/output_graph.json graph.png
```

## 输出文件

处理完成后，会在输出目录生成以下文件：

- `{prefix}_graph.json` - 图结构数据
- `{prefix}_stats.json` - 统计信息
- `{prefix}_chunks.json` - Chunk数据
- `{prefix}_entities.json` - 实体数据

## 图结构说明

### 节点类型

| 类型 | 说明 | 颜色 |
|------|------|------|
| document | 文档根节点 | 红色 |
| section | 章节节点 | 青色 |
| chunk | 文本块节点 | 蓝色 |
| entity | 实体节点 | 绿色 |

### 边类型

| 类型 | 说明 | 样式 |
|------|------|------|
| contains | 包含关系 | 实线 |
| next | 顺序关系 | 实线（弯曲） |
| mentions | 提及关系 | 虚线 |

## 配置说明

```python
from markdown_parser import ParserConfig, NERConfig, ChunkConfig, CleanerConfig

# 自定义配置
config = ParserConfig(
    ner=NERConfig(
        model_name="Davlan/bert-base-multilingual-cased-ner-hrl",
        device="cpu"
    ),
    chunk=ChunkConfig(
        min_tokens=100,
        max_tokens=500,
        target_tokens=300
    ),
    cleaner=CleanerConfig(
        min_content_length=10
    )
)

processor = MarkdownProcessor(config)
```

## 实体提取逻辑

1. **NER模型提取** - 使用预训练的多语言NER模型
2. **正则补充** - 补充提取电话、邮箱、日期等
3. **上下文分析** - 判断实体是否为结构化信息
4. **去重处理** - 移除重叠的实体

### 结构化实体识别

系统会根据实体周围的关键词判断是否为结构化信息：

- 签名区域：签名、签字、署名
- 日期区域：日期、时间、签字日期
- 联系方式：电话、手机、邮箱
- 单位信息：工作单位、学校、学院

## 分块策略

1. **按段落分割** - 首先按空行分割段落
2. **预计算Token** - 统计每个段落的token数
3. **智能合并** - 合并过短的段落
4. **边界分割** - 在句子边界处分割长文本
5. **重叠处理** - 可选的重叠分割策略
