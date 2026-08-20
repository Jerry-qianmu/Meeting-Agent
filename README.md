<p align="center">
  <h1 align="center">📚 MyAgent - 智能知识库管理系统</h1>
  <p align="center">基于 RAG 的智能问答知识库，支持文档管理、向量检索与 Agent 交互</p>
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
- 支持 PDF、TXT、Markdown 格式
- 智能 Markdown 分块（基于标题层级）
- 自动向量化与索引构建
- MinerU 集成解析复杂文档

### 🔍 智能检索
- **混合检索**: 向量检索 + 关键词检索
- **查询扩展**: 自动扩展相关查询
- **重排序**: 基于相关性的二次排序
- **质量控制**: 检索结果质量评估

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

**后端 `.env` 配置示例：**

```env
# MySQL 配置
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=knowledge_base
MYSQL_PORT=3306

# Milvus 配置
MILVUS_HOST=localhost
MILVUS_PORT=19530

# DashScope API (通义千问)
DASHSCOPE_API_KEY=your_api_key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# LLM 模型配置
GENERATION_MODEL=deepseek-v4-pro
REWRITE_MODEL=deepseek-v4-pro
RERANK_MODEL=qwen3-rerank

# Embedding 模型
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1536

# OSS 配置 (可选)
OSS_ACCESS_KEY_ID=your_access_key
OSS_ACCESS_KEY_SECRET=your_secret_key
OSS_REGION=cn-hangzhou
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET=your_bucket_name
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
├── frontend/                    # 前端项目
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


### ASR 功能待开发中

---


<p align="center">
  Made with ❤️ by MyAgent Team
</p>
