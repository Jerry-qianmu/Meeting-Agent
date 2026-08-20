# -*- coding: utf-8 -*-
"""
Memory Constellations 记忆系统数据库表结构定义

新增 6 张表，适配面试辅助 Agent 场景：
1. memory_fragment   - 记忆碎片（Scribe 提取的单条事实）
2. memory_entity     - 记忆实体（公司/职位/技术栈/面试官等）
3. memory_episode    - 记忆剧集（整合后的叙事段落）
4. memory_saga       - 记忆传奇（跨实体的长期叙事弧线）
5. cognitive_model   - 认知模型（AI 对候选人的理解画像）
6. memory_correction - 记忆修正（用户纠正记录）
"""

# -- 记忆碎片表（对应 Scribe 输出）
CREATE_TABLE_MEMORY_FRAGMENT = """
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
"""

# -- 记忆实体表（对应 Archivist 管理的实体）
CREATE_TABLE_MEMORY_ENTITY = """
CREATE TABLE IF NOT EXISTS memory_entity (
    entity_id CHAR(36) PRIMARY KEY COMMENT '实体唯一 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    name VARCHAR(200) NOT NULL COMMENT '实体名称',
    entity_type VARCHAR(50) NOT NULL COMMENT '实体类型: company/position/technology/interviewer/question/concept/project/event',
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
    INDEX idx_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='记忆实体表';
"""

# -- 记忆剧集表（对应整合后的叙事段落）
CREATE_TABLE_MEMORY_EPISODE = """
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
"""

# -- 记忆传奇表（对应跨实体的长期叙事弧线）
CREATE_TABLE_MEMORY_SAGA = """
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
"""

# -- 认知模型表（AI 对候选人的理解画像）
CREATE_TABLE_COGNITIVE_MODEL = """
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
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='认知模型表';
"""

# -- 记忆修正表（处理用户纠正）
CREATE_TABLE_MEMORY_CORRECTION = """
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
"""

# =========================
# 所有记忆系统 DDL 集合
# =========================
MEMORY_DDL_STATEMENTS = [
    CREATE_TABLE_MEMORY_FRAGMENT,
    CREATE_TABLE_MEMORY_ENTITY,
    CREATE_TABLE_MEMORY_EPISODE,
    CREATE_TABLE_MEMORY_SAGA,
    CREATE_TABLE_COGNITIVE_MODEL,
    CREATE_TABLE_MEMORY_CORRECTION,
]

MEMORY_TABLES = [
    'memory_fragment',
    'memory_entity',
    'memory_episode',
    'memory_saga',
    'cognitive_model',
    'memory_correction',
]
