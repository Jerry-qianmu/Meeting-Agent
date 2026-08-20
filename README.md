<p align="center">
  <h1 align="center">📚 AI面试Copilot</h1>
  <p align="center">基于 RAG 的智能问答知识库，支持文档管理、向量检索与 Agent 交互，ASR实时转译与意见提供</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/vue-3.4+-green.svg" alt="Vue">
  <img src="https://img.shields.io/badge/fastapi-0.109+-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/milvus-2.6+-00aaff.svg" alt="Milvus">
  <img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="License">
</p>

---

## ✨ 功能特性

### 📖 知识库管理
- 知识库 CRUD 操作
- 支持多知识库隔离管理
- 文档上传与处理状态跟踪

### 📄 文档处理
- 利用MinerU 进行文档处理,统一解析为Markdown格式，利用Vlm模型对解析后格式优化校正
- 智能 Markdown 分块（基于标题层级）
- 自动向量化与索引构建

### 🔍 智能检索
- **混合检索**: 向量检索 + 关键词检索，大范围rerank之后进行chunk merge,再进行二次rerank提高召回质量

### 🤖 Agent 系统
- LangGraph 驱动的 RAG Agent
- 多轮对话与上下文管理
- 自动记忆管理（短期/长期记忆）
- MCP 工具集成（Web 搜索等）

### 💾 记忆系统
- 短期记忆：对话上下文压缩
- 长期记忆：知识片段持久化
- 记忆整合与实体解析
- 认知模型服务

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Vue 3)                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │  Vite   │  │  Pinia  │  │ Router  │  │  Axios  │       │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Controllers │  │   Services   │  │    Agents    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│           │               │                │               │
│           ▼               ▼                ▼               │
│  ┌─────────────────────────────────────────────────┐       │
│  │              Database Layer                      │       │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐         │       │
│  │  │  MySQL  │  │ Milvus  │  │   OSS   │         │       │
│  │  └─────────┘  └─────────┘  └─────────┘         │       │
│  └─────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **前端** | Vue 3 + Vite + Tailwind CSS | 响应式 UI 界面 |
| **后端** | Python + FastAPI | REST API 服务 |
| **数据库** | MySQL | 结构化数据存储 |
| **向量库** | Milvus | 向量检索与相似度搜索 |
| **对象存储** | 阿里云 OSS | 文档文件存储 |
| **LLM** | DashScope / OpenAI 兼容接口 | 文本生成与理解 |
| **Agent** | LangChain + LangGraph | 智能对话流程 |
| **解析** | MinerU + Markdown Parser | 文档内容提取 |

---

## 🚀 快速开始

### 前置要求

- Python 3.10+
- Node.js 18+
- Docker & Docker Compose
- MySQL 8.0+
- 阿里云 OSS 账号（可选）

### 1. 克隆项目

```bash
git clone https://github.com/your-username/MyAgent.git
cd MyAgent
```

### 2. 启动 Milvus 向量数据库

```bash
# 使用 Docker Compose 启动 Milvus 及其依赖
docker-compose up -d

# 验证 Milvus 运行状态
curl http://localhost:9091/healthz
```

### 3. 配置后端环境

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env  # 如果有示例文件
# 或手动创建 .env 文件
```



### 4. 启动后端服务

```bash
# 开发模式启动
python main.py

# 或使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

后端服务将在 http://localhost:8000 启动，API 文档访问：http://localhost:8000/docs

### 5. 配置前端环境

```bash
cd ../frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端将在 http://localhost:5173 启动

---

## 📁 项目结构

```
MyAgent/
├── frontend/                    # 前端项目s
│   ├── src/
│   │   ├── api/                # API 接口定义
│   │   ├── views/              # 页面组件
│   │   ├── router/             # 路由配置
│   │   ├── App.vue             # 根组件
│   │   └── main.js             # 入口文件
│   ├── package.json
│   └── vite.config.js
│
├── backend/                     # 后端项目
│   ├── api_controller/         # API 控制器
│   │   ├── knowledge_base_controller.py
│   │   ├── document_controller.py
│   │   ├── agent_controller.py
│   │   ├── session_controller.py
│   │   └── auth_controller.py
│   ├── api_service/            # 业务逻辑层
│   ├── agents/                 # Agent 实现
│   │   └── knowledge/          # 知识库 Agent
│   ├── database/               # 数据库层
│   │   ├── mysql/              # MySQL 客户端
│   │   ├── milvus/             # Milvus 客户端
│   │   └── oss/                # OSS 客户端
│   ├── service/                # 服务层
│   │   ├── memory/             # 记忆系统
│   │   ├── chunking/           # 文档分块
│   │   └── MCP/                # MCP 工具
│   ├── config/                 # 配置文件
│   ├── main.py                 # 应用入口
│   └── requirements.txt        # Python 依赖
│
├── docs/                        # 项目文档
├── docker-compose.yml          # Milvus 部署配置
└── README.md                   # 项目说明
```

---

## 📡 API 接口

### 知识库管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/knowledge-bases` | 获取知识库列表 |
| `POST` | `/api/v1/knowledge-bases` | 创建知识库 |
| `GET` | `/api/v1/knowledge-bases/{id}` | 获取知识库详情 |
| `PUT` | `/api/v1/knowledge-bases/{id}` | 更新知识库 |
| `DELETE` | `/api/v1/knowledge-bases/{id}` | 删除知识库 |

### 文档管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/documents` | 获取文档列表 |
| `POST` | `/api/v1/documents/upload` | 上传文档 |
| `GET` | `/api/v1/documents/{id}` | 获取文档详情 |
| `DELETE` | `/api/v1/documents/{id}` | 删除文档 |

### Agent 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/agent/chat` | 发送消息给 Agent |
| `GET` | `/api/v1/sessions` | 获取会话列表 |
| `POST` | `/api/v1/sessions` | 创建新会话 |
| `GET` | `/api/v1/sessions/{id}/messages` | 获取会话消息 |

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 服务健康状态 |
| `GET` | `/` | API 根路径信息 |

---

## 🔧 配置说明

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MYSQL_HOST` | localhost | MySQL 主机地址 |
| `MYSQL_PORT` | 3306 | MySQL 端口 |
| `MILVUS_HOST` | localhost | Milvus 主机地址 |
| `MILVUS_PORT` | 19530 | Milvus 端口 |
| `DASHSCOPE_API_KEY` | - | DashScope API 密钥 |
| `EMBEDDING_MODEL` | text-embedding-v4 | Embedding 模型 |
| `GENERATION_MODEL` | deepseek-v4-pro | 生成模型 |
| `RERANK_MODEL` | qwen3-rerank | 重排序模型 |
| `FASTAPI_PORT` | 8000 | 后端服务端口 |
| `FASTAPI_DEBUG` | false | 调试模式 |

### 检索配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `TOP_K` | 10 | 返回文档数量 |
| `SEARCH_LIMIT` | 50 | 搜索候选池大小 |
| `RERANK_LIMIT` | 40 | 重排序候选数量 |
| `RERANK_FINAL_TOP_K` | 20 | 最终返回数量 |
| `HYBRID_ALPHA` | 0.7 | 混合检索权重 |

---

## 📊 数据库设计

### MySQL 表结构

- `knowledge_bases` - 知识库表
- `documents` - 文档表
- `chunks` - 文档分块表
- `sessions` - 会话表
- `messages` - 消息表
- `users` - 用户表
- `memory_fragments` - 记忆片段表
- `memory_entities` - 记忆实体表

### Milvus Collections

- 文档向量 Collection（自动创建）
- 支持动态字段过滤
- 混合检索（向量 + 标量）

---

## 🧪 测试与评估

```bash
cd backend

# 运行 RAGAS 评估
python eval/ragas_eval.py
```

---


### 🎙️ 会议实时转写系统 (Meeting Transcriber)

基于 ASR 的会议/面试实时转写与智能建议系统，支持双流音频采集、实时转写、LLM 建议生成。

#### 核心功能

- **双流音频采集**: 同时采集麦克风（自己）和系统音频（对方/面试官）
- **实时 ASR 转写**: 支持批量和流式两种 ASR 模式，自动语言检测
- **智能建议生成**: 基于 LLM 分析对话上下文，实时生成面试/会议建议
- **桌面 GUI 应用**: 基于 tkinter 的可视化界面，支持实时显示转写和建议
- **会议报告导出**: 自动生成 Markdown 格式的会议记录报告

#### 技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Meeting Transcriber                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Audio Layer │  │   ASR Layer  │  │  Advisor     │         │
│  │  ┌─────────┐ │  │  ┌─────────┐ │  │  ┌─────────┐ │         │
│  │  │Recorder │ │  │  │Gradio   │ │  │  │Suggestion│ │         │
│  │  │Capture  │ │  │  │ASR      │ │  │  │Engine   │ │         │
│  │  │Device   │ │  │  │Streaming│ │  │  │Prompts  │ │         │
│  │  │Manager  │ │  │  │Merger   │ │  │  │         │ │         │
│  │  └─────────┘ │  │  └─────────┘ │  │  └─────────┘ │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│           │               │                │                   │
│           ▼               ▼                ▼                   │
│  ┌─────────────────────────────────────────────────┐           │
│  │              Output Layer                        │           │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐         │           │
│  │  │  GUI    │  │  REST   │  │WebSocket│         │           │
│  │  │(tkinter)│  │   API   │  │   API   │         │           │
│  │  └─────────┘  └─────────┘  └─────────┘         │           │
│  └─────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

#### 模块说明

| 模块 | 路径 | 功能 |
|------|------|------|
| **audio** | `meeting_transcriber/audio/` | 音频采集、设备管理、录音器 |
| **asr** | `meeting_transcriber/asr/` | ASR 识别、流式处理、结果合并 |
| **advisor** | `meeting_transcriber/advisor/` | LLM 建议引擎、Prompt 模板 |
| **report** | `meeting_transcriber/report/` | Markdown 报告生成 |
| **api** | `meeting_transcriber/api/` | REST API、WebSocket 接口 |
| **gui** | `meeting_transcriber/gui.py` | tkinter 桌面应用 |

#### 快速启动

```bash
cd meeting_transcriber

# 安装依赖
pip install -r requirements.txt

# 方式 1: 启动 FastAPI 服务 (默认端口 8200)
python main.py

# 方式 2: 启动桌面 GUI 应用
python main.py --gui
```

#### 配置说明

在项目根目录或 `meeting_transcriber/` 下创建 `.env` 文件：

```env
# ASR 服务配置
ASR_SERVER_URL=http://localhost:8101    # ASR 服务地址
ASR_LANGUAGE=Auto                        # 语言 (Auto/zh/en/ja/ko)

# 音频配置
AUDIO_SAMPLE_RATE=16000                  # 采样率
AUDIO_CHANNELS=1                         # 声道数
AUDIO_CHUNK_DURATION=4.0                 # 分段时长（秒）

# LLM 建议配置
DASHSCOPE_API_KEY=your_api_key           # DashScope API 密钥
SUGGESTION_MODEL=deepseek-v4-pro         # 建议生成模型
SUGGESTION_MIN_INTERVAL=15.0             # 最小建议间隔（秒）
SUGGESTION_TIME_TRIGGER=45.0             # 定时触发间隔（秒）
SUGGESTION_CONTEXT_ROUNDS=10             # 上下文窗口轮数

# ASR 模式
ASR_MODE=batch                           # batch 或 streaming

# 服务配置
MEETING_HOST=0.0.0.0                     # 服务地址
MEETING_PORT=8200                        # 服务端口
MEETING_DEBUG=false                      # 调试模式

# 报告输出
REPORT_OUTPUT_DIR=./meeting_reports      # 报告保存目录
```

#### API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/meeting/start` | 开始录制 |
| `POST` | `/api/v1/meeting/stop` | 停止录制 |
| `GET` | `/api/v1/meeting/status` | 获取录制状态 |
| `GET` | `/api/v1/meeting/transcripts` | 获取转写记录 |
| `GET` | `/api/v1/meeting/suggestions` | 获取建议列表 |
| `WS` | `/ws/meeting/{session_id}` | WebSocket 实时推送 |

#### 数据模型

- **AudioSegment**: 音频片段（含说话人标记、时间戳、采样率）
- **TranscriptSegment**: 转写结果（含识别文本、语言、是否最终结果）
- **Suggestion**: LLM 生成的建议（含内容、上下文摘要）
- **MeetingSession**: 会议会话（含场景、转写记录、建议记录）

#### 场景支持

- **面试模式** (INTERVIEW): 针对面试场景优化的建议 Prompt
- **会议模式** (MEETING): 通用会议记录与建议
- **自定义模式** (CUSTOM): 可扩展的自定义场景

#### 依赖项

```
# audio
pyaudiowpatch>=0.2.12    # Windows 音频采集
numpy>=1.24.0

# asr
gradio_client>=1.3.0     # Gradio ASR 客户端

# llm
dashscope>=1.20.0        # 阿里云 DashScope

# api
fastapi>=0.115.0
uvicorn>=0.32.0
websockets>=12.0

# utilities
pydantic>=2.0.0
python-dotenv>=1.0.0
```

---


<p align="center">
  Made with ❤️ by MyAgent Team
</p>
