# Memory Constellations 记忆架构迁移计划

> 将 MemoryConstellations 的分层自组织记忆架构迁移到面试辅助 Agent 中
> 技术栈：Python + FastAPI + LangGraph + MySQL + Milvus + DashScope

---

## 一、架构映射总览

### 1.1 原始架构 → 面试场景映射

| MemoryConstellations 概念 | 面试 Agent 适配 | 说明 |
|--------------------------|----------------|------|
| **Scribe（书记官）** | **InterviewScribe** | 从面试对话中提取面试相关事实碎片 |
| **Archivist（档案管理员）** | **InterviewArchivist** | 将碎片组织为实体、剧集、传奇 |
| **Librarian（图书管理员）** | **InterviewLibrarian** | 三通道混合检索 + RRF 融合 |
| **Fragments（碎片）** | **MemoryFragment** | 单条面试事实（≤150字符） |
| **Entities（实体）** | **MemoryEntity** | 面试实体：公司/职位/技术栈/面试官/候选人 |
| **Episodes（剧集）** | **MemoryEpisode** | 一次完整面试的叙事段落 |
| **Sagas（传奇）** | **MemorySaga** | 跨多次面试的职业发展叙事弧线 |
| **Cognitive Model** | **CognitiveModel** | 候选人当前状态画像（技术掌握度/面试焦虑度等） |
| **Lifecycle Engine** | **MemoryLifecycle** | 记忆衰减与清理 |

### 1.2 面试场景的实体类型定义

```python
class EntityType(str, Enum):
    COMPANY = "company"          # 公司（字节、腾讯、阿里...）
    POSITION = "position"        # 职位（后端开发、算法工程师...）
    TECHNOLOGY = "technology"    # 技术栈（Python、Redis、MySQL...）
    INTERVIEWER = "interviewer"  # 面试官
    QUESTION = "question"        # 面试题（高频出现的问题模式）
    CONCEPT = "concept"          # 技术概念（TCP三次握手、红黑树...）
    PROJECT = "project"          # 项目经历
    EVENT = "event"              # 面试事件（某次面试、某次笔试...）
```

---

## 二、数据库设计（新增表）

> 基于现有 MySQL 数据库，新增 6 张表，复用已有的 `short_term_memory` 和 `long_term_memory` 表

### 2.1 新增表

```sql
-- 1. 记忆碎片表（对应 Scribe 输出）
CREATE TABLE IF NOT EXISTS memory_fragment (
    fragment_id CHAR(36) PRIMARY KEY COMMENT '碎片唯一 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    session_uuid CHAR(36) DEFAULT NULL COMMENT '来源会话 ID',
    message_uuid CHAR(36) DEFAULT NULL COMMENT '来源消息 ID',
    content VARCHAR(500) NOT NULL COMMENT '碎片内容（第三人称，≤150字）',
    fragment_type VARCHAR(50) NOT NULL DEFAULT 'fact' COMMENT '类型: fact/preference/feedback/experience',
    entity_id CHAR(36) DEFAULT NULL COMMENT '关联实体 ID（分类后填入）',
    consolidated BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否已整合为 episode',
    importance_score FLOAT NOT NULL DEFAULT 0.5 COMMENT '重要性分数 (0-1)',
    access_count INT NOT NULL DEFAULT 0 COMMENT '访问次数',
    last_accessed_at TIMESTAMP NULL COMMENT '最后访问时间',
    lifecycle_status VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT 'active/cooling/frozen/tombstone',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,

    INDEX idx_user_created (user_id, created_at DESC),
    INDEX idx_entity (entity_id),
    INDEX idx_consolidated (consolidated),
    INDEX idx_lifecycle (lifecycle_status),
    INDEX idx_session (session_uuid),
    INDEX idx_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='记忆碎片表';

-- 2. 记忆实体表（对应 Archivist 管理的实体）
CREATE TABLE IF NOT EXISTS memory_entity (
    entity_id CHAR(36) PRIMARY KEY COMMENT '实体唯一 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    name VARCHAR(200) NOT NULL COMMENT '实体名称',
    entity_type VARCHAR(50) NOT NULL COMMENT '实体类型',
    description TEXT COMMENT '实体描述/概述',
    fragment_count INT NOT NULL DEFAULT 0 COMMENT '关联碎片数量',
    episode_count INT NOT NULL DEFAULT 0 COMMENT '关联剧集数量',
    importance_score FLOAT NOT NULL DEFAULT 0.5 COMMENT '重要性分数',
    status VARCHAR(20) NOT NULL DEFAULT 'seed' COMMENT 'seed/active/mature/archived',
    metadata JSON COMMENT '扩展元数据',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,

    INDEX idx_user_type (user_id, entity_type),
    INDEX idx_name (name),
    INDEX idx_status (status),
    INDEX idx_importance (importance_score DESC),
    UNIQUE KEY uk_user_name_type (user_id, name, entity_type, deleted_at),
    INDEX idx_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='记忆实体表';

-- 3. 记忆剧集表（对应整合后的叙事段落）
CREATE TABLE IF NOT EXISTS memory_episode (
    episode_id CHAR(36) PRIMARY KEY COMMENT '剧集唯一 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    entity_id CHAR(36) DEFAULT NULL COMMENT '主实体 ID',
    title VARCHAR(300) NOT NULL COMMENT '剧集标题',
    content TEXT NOT NULL COMMENT '叙事内容（100-500字）',
    episode_type VARCHAR(50) NOT NULL DEFAULT 'interview' COMMENT '类型: interview/practice/feedback/learning',
    fragment_ids JSON COMMENT '整合的碎片 ID 列表',
    importance_score FLOAT NOT NULL DEFAULT 0.5,
    lifecycle_status VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT 'active/mature/archived',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_user_created (user_id, created_at DESC),
    INDEX idx_entity (entity_id),
    INDEX idx_type (episode_type),
    INDEX idx_lifecycle (lifecycle_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='记忆剧集表';

-- 4. 记忆传奇表（对应跨实体的长期叙事弧线）
CREATE TABLE IF NOT EXISTS memory_saga (
    saga_id CHAR(36) PRIMARY KEY COMMENT '传奇唯一 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    title VARCHAR(300) NOT NULL COMMENT '传奇标题',
    summary TEXT NOT NULL COMMENT '叙事弧线摘要',
    saga_type VARCHAR(50) NOT NULL DEFAULT 'career' COMMENT '类型: career/technical/growth/challenge',
    entity_ids JSON COMMENT '涉及的实体 ID 列表',
    episode_ids JSON COMMENT '包含的剧集 ID 列表',
    emotion_axes JSON COMMENT '情感轴（信心/焦虑/准备度）',
    importance_score FLOAT NOT NULL DEFAULT 0.7,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_user_type (user_id, saga_type),
    INDEX idx_importance (importance_score DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='记忆传奇表';

-- 5. 认知模型表（AI 对候选人的理解画像）
CREATE TABLE IF NOT EXISTS cognitive_model (
    model_id CHAR(36) PRIMARY KEY COMMENT '模型条目 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID（被描述的候选人）',
    dimension VARCHAR(100) NOT NULL COMMENT '维度: tech_skill/interview_confidence/weakness/strength/preparation_level',
    dimension_key VARCHAR(200) NOT NULL COMMENT '维度细分键',
    current_value TEXT NOT NULL COMMENT '当前状态描述',
    confidence FLOAT NOT NULL DEFAULT 0.5 COMMENT '置信度 (0-1)',
    evidence_count INT NOT NULL DEFAULT 1 COMMENT '支撑证据数量',
    ttl_days INT NOT NULL DEFAULT 90 COMMENT '有效期（天）',
    expires_at TIMESTAMP NULL COMMENT '过期时间',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_user_dim (user_id, dimension),
    INDEX idx_expires (expires_at),
    UNIQUE KEY uk_user_dim_key (user_id, dimension, dimension_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='认知模型表';

-- 6. 记忆修正表（处理用户纠正）
CREATE TABLE IF NOT EXISTS memory_correction (
    correction_id CHAR(36) PRIMARY KEY COMMENT '修正 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    original_fragment_id CHAR(36) DEFAULT NULL COMMENT '被修正的碎片 ID',
    original_content VARCHAR(500) COMMENT '原始内容',
    corrected_content VARCHAR(500) NOT NULL COMMENT '修正后内容',
    correction_type VARCHAR(50) NOT NULL COMMENT 'fix_fragment/new_correction',
    reason TEXT COMMENT '修正原因',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_user (user_id),
    INDEX idx_original (original_fragment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='记忆修正表';
```

### 2.2 复用现有表

- `short_term_memory` → 保留作为 Scribe 的原始输入缓冲（对话级短期记忆）
- `long_term_memory` → 保留，与新系统共存（可选择渐进迁移）
- `message` → Scribe 从中提取碎片
- `session` → 碎片关联来源

---

## 三、服务架构设计

### 3.1 新增文件结构

```
backend/
  service/
    memory/                              # 新增记忆系统目录
      __init__.py
      scribe.py                          # 碎片提取器
      archivist.py                       # 记忆组织者
      librarian.py                       # 记忆检索器
      lifecycle.py                       # 生命周期引擎
      cognitive_model_service.py         # 认知模型服务
      entity_resolver.py                 # 实体识别与消歧
      consolidator.py                    # 碎片→剧集整合器
      saga_builder.py                    # 剧集→传奇构建器
      prompts.py                         # 所有 LLM 提示词
      config.py                          # 记忆系统配置
      models.py                          # 数据模型（dataclass/pydantic）

  database/
    mysql/
      repository/
        memory_fragment_repository.py    # 碎片数据访问
        memory_entity_repository.py      # 实体数据访问
        memory_episode_repository.py     # 剧集数据访问
        memory_saga_repository.py        # 传奇数据访问
        cognitive_model_repository.py    # 认知模型数据访问
        memory_correction_repository.py  # 修正数据访问

  agents/
    knowledge/
      node/
        memory_scribe_node.py            # LangGraph 节点：碎片提取
        memory_retrieval_node.py         # LangGraph 节点：记忆检索注入
```

### 3.2 服务详细设计

#### 3.2.1 Scribe（碎片提取器） — `service/memory/scribe.py`

**触发条件**：会话结束 / 每 10 轮对话 / 消息积压 ≥ 50 条

```python
class InterviewScribe:
    """从面试对话中提取记忆碎片"""

    async def extract_from_session(self, session_id: str, user_id: str) -> List[MemoryFragment]:
        """从完整会话中提取碎片"""
        messages = self.message_repo.get_session_messages(session_id)
        # LLM 提取 → 存入 memory_fragment 表 → 索引到 Milvus

    async def extract_incremental(self, session_id: str, user_id: str,
                                   new_messages: List[Dict]) -> List[MemoryFragment]:
        """增量提取（仅处理新消息）"""
```

#### 3.2.2 Archivist（记忆组织者） — `service/memory/archivist.py`

**运行模式**：每 2 分钟 tick，分轻量/深度两种模式

```python
class InterviewArchivist:
    async def tick(self):
        # 轻量模式（无 LLM）
        self._link_fragments_to_entities()
        self._update_evidence_counters()
        self._expire_stale_entries()
        self._merge_duplicate_entities()

        # 深度周期（用户空闲 ≥ 阈值时，LLM 密集）
        if self._should_deep_cycle():
            await self._classify_unlinked_fragments()
            await self._grow_seed_entities()
            await self._consolidate_fragments()      # 碎片 → 剧集
            await self._cluster_sagas()              # 剧集 → 传奇
            await self._discover_emergent_entities()
            await self._regenerate_entity_overviews()
```

#### 3.2.3 Librarian（记忆检索器） — `service/memory/librarian.py`

```python
class InterviewLibrarian:
    """三通道混合检索 + RRF 融合"""

    async def search(self, query: str, user_id: str, top_k: int = 10):
        # 1. Milvus BM25 关键词搜索
        keyword_results = await self._keyword_search(query, user_id)
        # 2. Milvus dense vector 向量相似度搜索
        vector_results = await self._vector_search(query, user_id)
        # 3. 实体聚合搜索
        entity_results = await self._entity_aggregation(query, user_id)
        # RRF 融合 + Episodes 1.5x 权重加成
        return self._rrf_fusion(keyword_results, vector_results, entity_results)
```

#### 3.2.4 Lifecycle（生命周期引擎） — `service/memory/lifecycle.py`

```python
class MemoryLifecycle:
    LIFECYCLE_RULES = {
        'fragment': {
            'active_to_cooling_days': 14,
            'cooling_to_frozen_days': 30,
            'frozen_to_tombstone_days': 90,
        },
        'episode': {
            'active_to_mature_months': 6,
            'mature_to_archived_months': 12,
        }
    }

    async def run_cleanup(self):
        """定期清理（建议每天一次）"""
        await self._transition_fragments()
        await self._transition_episodes()
        await self._expire_cognitive_model()
        await self._cleanup_tombstones()
```

---

## 四、LangGraph 集成方案

### 4.1 新增节点

```
现有流程：
START → memory_manager → query_rewrite → ... → generate_answer → END

新增后：
START → memory_manager → [memory_scribe_node] → query_rewrite → ...
    → generate_answer → [memory_retrieval_node] → END
```

### 4.2 定时任务

```python
# main.py
@app.on_event("startup")
async def start_memory_archivist():
    archivist = InterviewArchivist(db_client, milvus_service, llm_service)
    asyncio.create_task(archivist.start_tick_loop(interval_seconds=120))
```

---

## 五、Milvus 集成方案

### 5.1 记忆向量集合

```python
MEMORY_COLLECTION_NAME = "memory_fragments_{user_id}"
# Schema: fragment_id, content, dense_vector(1024), sparse_vector, entity_id, fragment_type, importance_score, created_at

EPISODE_COLLECTION_NAME = "memory_episodes_{user_id}"
# Schema: episode_id, content, dense_vector(1024), entity_id, episode_type, importance_score
```

---

## 六、实现分期计划

### Phase 1：基础碎片系统 ✅ [状态：已完成]
- [x] 新增 6 张数据库表（DDL + 迁移脚本） → `database/mysql/memory_schema.py`
- [x] 实现 6 个 Repository 类 → `database/mysql/repository/memory_*_repository.py`
- [x] 实现 `InterviewScribe`（碎片提取） → `service/memory/scribe.py`
- [x] 实现 `entity_resolver.py`（基础实体识别） → `service/memory/entity_resolver.py`
- [x] LangGraph 集成 `memory_scribe_node` → `agents/knowledge/node/memory_scribe_node.py`
- [x] 记忆检索注入节点 → `agents/knowledge/node/memory_retrieval_node.py`
- [x] 状态字段 `memory_context` → `agents/knowledge/state.py`
- [x] 图节点注册 + 边连接 → `agents/knowledge/graph.py`
- [x] generate_answer 三路径注入 memory_context → `agents/knowledge/node/generate_answer.py`
- [x] 数据模型定义 → `service/memory/models.py`
- [x] 配置文件 → `service/memory/config.py`
- [x] LLM 提示词 → `service/memory/prompts.py`
- [x] 数据库初始化集成 → `database/mysql/database_schema.py`, `init_database.py`
- [ ] 基础碎片 Milvus 索引（待 Phase 3 与 Librarian 一起实现）

### Phase 2：实体与整合系统 ✅ [状态：已完成]
- [x] 实现 `InterviewArchivist`（轻量模式 + 深度周期） → `service/memory/archivist.py`
- [x] 实现 `Consolidator`（碎片 → 剧集） → `service/memory/consolidator.py`
- [x] 实体自动发现与合并 → Archivist._lightweight_link + _merge_duplicate_entities
- [x] 后台定时任务集成 → `main.py` lifespan 启动 Archivist tick 循环
- [x] 基础碎片/剧集 Milvus 索引 → `service/memory/memory_milvus_service.py` + Scribe/Consolidator/Librarian 集成

### Phase 3：检索与注入系统 ✅ [状态：已完成]
- [x] 实现 `InterviewLibrarian`（三通道 RRF 检索） → `service/memory/librarian.py`
- [x] 修改 `generate_answer.py` 注入记忆上下文 → Phase 1 已完成
- [x] 实现认知模型服务 → `service/memory/cognitive_model_service.py`
- [x] 升级 `memory_retrieval_node` 使用 Librarian → `agents/knowledge/node/memory_retrieval_node.py`
- [x] 后台定时任务集成 → Phase 2 已完成

### Phase 4：高级功能 ⏳ [状态：待实现]
- [ ] 实现 `saga_builder.py`（剧集 → 传奇）
- [ ] 实现 `lifecycle.py`（生命周期引擎）
- [ ] 记忆修正工具
- [ ] 面试状态追踪（可选）
- [ ] 星图可视化 API

---

## 七、配置项

```python
class MemoryConfig:
    SCRIBE_TRIGGER_SILENCE_MINUTES = 20
    SCRIBE_BACKLOG_THRESHOLD = 50
    SCRIBE_MAX_FRAGMENT_LENGTH = 150
    ARCHIVIST_TICK_INTERVAL_SECONDS = 120
    ARCHIVIST_DEEP_CYCLE_IDLE_MINUTES = 60
    LIBRARIAN_EPISODE_BOOST = 1.5
    LIBRARIAN_VECTOR_FLOOR = 0.3
    LIBRARIAN_TOP_K = 10
    FRAGMENT_ACTIVE_TO_COOLING_DAYS = 14
    FRAGMENT_COOLING_TO_FROZEN_DAYS = 30
    FRAGMENT_FROZEN_TO_TOMBSTONE_DAYS = 90
    EPISODE_ACTIVE_TO_MATURE_MONTHS = 6
    EPISODE_MATURE_TO_ARCHIVED_MONTHS = 12
    ENTITY_SEED_GRADUATE_THRESHOLD = 3
    ENTITY_MERGE_SIMILARITY_THRESHOLD = 0.8
```

---

## 八、与现有系统的兼容性

1. **短期记忆系统**：保留 `ShortTermMemoryService`，作为 Scribe 输入缓冲
2. **长期记忆系统**：保留 `long_term_memory` 表，新系统并行运行
3. **LangGraph 状态**：新增 `memory_context` 字段到 `KnowledgeAgentState`
4. **API 接口**：新增记忆相关 REST API
5. **LLM 调用**：复用 DashScope 配置，Scribe 用 flash，Archivist 深度周期用 pro
