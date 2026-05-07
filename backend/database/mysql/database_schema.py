# -*- coding: utf-8 -*-
"""
MySQL 数据库表结构定义

设计原则：
1. 所有 UUID 字段统一使用 CHAR(36) 字符串格式，避免 hex/bytes 混用
2. 短期记忆：长期存储，使用时间衰减权重（而非过期删除）
3. 长期记忆：MySQL + Milvus 双存储，MySQL 存元数据，Milvus 存向量
4. 使用逻辑约束而非物理外键，提升性能
5. Repository 层通过代码逻辑保证数据一致性

ID 格式统一：
- 所有 ID 字段使用 CHAR(36) 存储 UUID 字符串
- 示例：'550e8400-e29b-41d4-a716-446655440000'
- 生成：str(uuid.uuid4())
"""

# =========================
# 外键约束开关
# =========================
# False = 逻辑约束（生产环境，默认）
# True = 物理外键约束（测试环境）
FK_CONSTRAINTS_ENABLED = False

# =========================
# 数据库初始化 DDL 语句
# =========================

INIT_DATABASE_DDL = [
    "SET NAMES utf8mb4",
    "SET CHARACTER SET utf8mb4",
]

# =========================
# 核心业务表
# =========================

# -- 用户表
CREATE_TABLE_USER = """
CREATE TABLE IF NOT EXISTS user (
    user_id CHAR(36) PRIMARY KEY COMMENT '用户唯一 ID (UUID 字符串)',
    username VARCHAR(100) NOT NULL COMMENT '用户名',
    email VARCHAR(255) DEFAULT NULL COMMENT '邮箱',
    password_hash VARCHAR(255) NOT NULL COMMENT 'bcrypt 加密密码',
    avatar_url VARCHAR(500) DEFAULT NULL COMMENT '头像 OSS 路径',
    display_name VARCHAR(100) DEFAULT NULL COMMENT '显示名称',
    timezone VARCHAR(50) DEFAULT 'UTC' COMMENT '时区设置',
    language VARCHAR(10) DEFAULT 'zh-CN' COMMENT '语言偏好',
    status TINYINT(1) NOT NULL DEFAULT 1 COMMENT '状态：0=禁用，1=启用，2=锁定',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    last_login_at TIMESTAMP DEFAULT NULL COMMENT '最后登录时间',
    login_count INT NOT NULL DEFAULT 0 COMMENT '登录次数',
    deleted_at TIMESTAMP DEFAULT NULL COMMENT '软删除时间 (NULL=未删除)',
    
    UNIQUE KEY uk_username (username),
    UNIQUE KEY uk_email (email),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at DESC),
    INDEX idx_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';
"""

# -- 会话表
CREATE_TABLE_SESSION = """
CREATE TABLE IF NOT EXISTS session (
    session_uuid CHAR(36) PRIMARY KEY COMMENT '会话唯一 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    title VARCHAR(255) DEFAULT NULL COMMENT '会话标题',
    summary TEXT DEFAULT NULL COMMENT '会话摘要',
    status TINYINT(1) NOT NULL DEFAULT 1 COMMENT '状态：0=归档，1=进行中，2=软删除',
    message_count INT NOT NULL DEFAULT 0 COMMENT '消息数量',
    token_count BIGINT NOT NULL DEFAULT 0 COMMENT '总 token 消耗',
    knowledge_base_ids JSON DEFAULT NULL COMMENT '选中的知识库 ID 列表',
    document_ids JSON DEFAULT NULL COMMENT '选中的文档 ID 列表',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后活动时间',
    deleted_at TIMESTAMP DEFAULT NULL COMMENT '软删除时间 (NULL=未删除)',
    
    INDEX idx_user_status (user_id, status),
    INDEX idx_updated_at (updated_at DESC),
    INDEX idx_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话表';
"""

# -- 消息表
CREATE_TABLE_MESSAGE = """
CREATE TABLE IF NOT EXISTS message (
    message_uuid CHAR(36) PRIMARY KEY COMMENT '消息唯一 ID',
    session_uuid CHAR(36) NOT NULL COMMENT '会话 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID (冗余)',
    role TINYINT(1) NOT NULL COMMENT '角色：0=user, 1=assistant, 2=system, 3=tool',
    content MEDIUMTEXT NOT NULL COMMENT '消息内容',
    parent_message_id CHAR(36) DEFAULT NULL COMMENT '父消息 ID (支持分支对话)',
    tool_calls JSON DEFAULT NULL COMMENT '工具调用记录',
    model_used VARCHAR(100) DEFAULT NULL COMMENT '使用的 LLM 模型',
    tokens_prompt INT DEFAULT NULL COMMENT 'prompt token 数',
    tokens_completion INT DEFAULT NULL COMMENT 'completion token 数',
    tokens_total INT DEFAULT NULL COMMENT '总 token 数',
    latency_ms INT DEFAULT NULL COMMENT '响应耗时 (毫秒)',
    status TINYINT(1) NOT NULL DEFAULT 1 COMMENT '状态：0=草稿，1=完成，2=失败',
    error_message TEXT DEFAULT NULL COMMENT '错误信息',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    deleted_at TIMESTAMP DEFAULT NULL COMMENT '软删除时间 (NULL=未删除)',
    
    INDEX idx_session_created (session_uuid, created_at),
    INDEX idx_user_created (user_id, created_at DESC),
    INDEX idx_role (role),
    INDEX idx_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='消息表';
"""

# =========================
# 知识库与文档表
# =========================

# -- 知识库表
CREATE_TABLE_KNOWLEDGE_BASE = """
CREATE TABLE IF NOT EXISTS knowledge_base (
    kb_uuid CHAR(36) PRIMARY KEY COMMENT '知识库唯一 ID',
    user_id CHAR(36) NOT NULL COMMENT '所有者用户 ID',
    name VARCHAR(255) NOT NULL COMMENT '知识库名称',
    description TEXT DEFAULT NULL COMMENT '知识库描述',
    collection_name VARCHAR(100) DEFAULT NULL COMMENT 'Milvus collection 名称',
    doc_count INT NOT NULL DEFAULT 0 COMMENT '文档数量',
    chunk_count INT NOT NULL DEFAULT 0 COMMENT '切片数量',
    total_tokens BIGINT NOT NULL DEFAULT 0 COMMENT '总 token 数',
    embedding_model VARCHAR(100) DEFAULT 'text-embedding-v4' COMMENT 'embedding 模型',
    status TINYINT(1) NOT NULL DEFAULT 1 COMMENT '状态：0=禁用，1=可用，2=处理中',
    is_private BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否私有',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted_at TIMESTAMP DEFAULT NULL COMMENT '软删除时间 (NULL=未删除)',
    
    INDEX idx_user_status (user_id, status),
    INDEX idx_collection (collection_name),
    INDEX idx_deleted_at (deleted_at),
    UNIQUE KEY uk_user_name (user_id, name, deleted_at) COMMENT '同一用户下知识库名称唯一（软删除时允许重名）'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库表';
"""

# -- 文档表
CREATE_TABLE_DOCUMENT = """
CREATE TABLE IF NOT EXISTS document (
    doc_uuid CHAR(36) PRIMARY KEY COMMENT '文档唯一 ID',
    kb_uuid CHAR(36) NOT NULL COMMENT '知识库 ID',
    user_id CHAR(36) NOT NULL COMMENT '上传用户 ID',
    title VARCHAR(255) DEFAULT NULL COMMENT '文档标题',
    original_filename VARCHAR(500) NOT NULL COMMENT '原始文件名',
    file_extension VARCHAR(10) NOT NULL COMMENT '文件扩展名',
    file_size BIGINT NOT NULL COMMENT '文件大小 (字节)',
    oss_path VARCHAR(1000) NOT NULL COMMENT 'OSS 存储路径',
    oss_bucket VARCHAR(100) DEFAULT NULL COMMENT 'OSS 存储桶名称',
    total_chunks INT NOT NULL DEFAULT 0 COMMENT '总切片数',
    processed_chunks INT NOT NULL DEFAULT 0 COMMENT '已处理切片数',
    chunk_count INT NOT NULL DEFAULT 0 COMMENT '最终切片数量',
    total_tokens BIGINT NOT NULL DEFAULT 0 COMMENT '总 token 数',
    status TINYINT(1) NOT NULL DEFAULT 0 COMMENT '状态：0=pending, 1=processing, 2=done, 3=failed',
    processing_error TEXT DEFAULT NULL COMMENT '处理错误信息',
    version INT NOT NULL DEFAULT 1 COMMENT '版本号',
    metadata JSON DEFAULT NULL COMMENT '扩展元数据',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted_at TIMESTAMP DEFAULT NULL COMMENT '软删除时间 (NULL=未删除)',
    
    INDEX idx_kb_status (kb_uuid, status),
    INDEX idx_user (user_id),
    INDEX idx_created_at (created_at DESC),
    INDEX idx_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文档表';
"""

# -- 文档切片表
CREATE_TABLE_CHUNK = """
CREATE TABLE IF NOT EXISTS chunk (
    chunk_uuid CHAR(36) PRIMARY KEY COMMENT '切片唯一 ID',
    doc_uuid CHAR(36) NOT NULL COMMENT '文档 ID',
    kb_uuid CHAR(36) NOT NULL COMMENT '知识库 ID (冗余)',
    content MEDIUMTEXT NOT NULL COMMENT '切片文本内容',
    chunk_order INT NOT NULL COMMENT '在文档中的顺序',
    start_char INT DEFAULT NULL COMMENT '原始文档起始字符位置',
    end_char INT DEFAULT NULL COMMENT '原始文档结束字符位置',
    page_number INT DEFAULT NULL COMMENT 'PDF 页码',
    section_title VARCHAR(500) DEFAULT NULL COMMENT '所属章节标题',
    token_count INT NOT NULL COMMENT 'token 数量',
    metadata JSON DEFAULT NULL COMMENT '扩展元数据',
    prev_chunk_id CHAR(36) DEFAULT NULL COMMENT '前一个切片 ID',
    next_chunk_id CHAR(36) DEFAULT NULL COMMENT '后一个切片 ID',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted_at TIMESTAMP DEFAULT NULL COMMENT '软删除时间 (NULL=未删除)',
    
    INDEX idx_doc_order (doc_uuid, chunk_order),
    INDEX idx_kb (kb_uuid),
    INDEX idx_section (section_title(100)),
    INDEX idx_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文档切片表';
"""

# =========================
# 记忆系统表
# =========================

# -- 短期记忆表（长期存储，使用时间衰减权重）
CREATE_TABLE_SHORT_TERM_MEMORY = """
CREATE TABLE IF NOT EXISTS short_term_memory (
    memory_id CHAR(36) PRIMARY KEY COMMENT '记忆唯一 ID',
    session_uuid CHAR(36) NOT NULL COMMENT '会话 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    query_summary VARCHAR(500) DEFAULT NULL COMMENT '问题摘要',
    answer_summary VARCHAR(1000) DEFAULT NULL COMMENT '答案摘要',
    entities JSON DEFAULT NULL COMMENT '提取的实体',
    key_facts JSON DEFAULT NULL COMMENT '关键事实',
    message_uuid CHAR(36) DEFAULT NULL COMMENT '关联的消息 ID',
    base_relevance_score FLOAT NOT NULL DEFAULT 1.0 COMMENT '基础相关性分数 (0-1)',
    access_count INT NOT NULL DEFAULT 1 COMMENT '访问次数',
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '最后访问时间',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    deleted_at TIMESTAMP DEFAULT NULL COMMENT '软删除时间 (NULL=未删除)',
    
    INDEX idx_session (session_uuid, created_at DESC),
    INDEX idx_user (user_id),
    INDEX idx_last_accessed (last_accessed_at DESC),
    INDEX idx_base_relevance (base_relevance_score DESC),
    INDEX idx_created_at (created_at DESC),
    INDEX idx_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短期记忆表（长期存储，时间衰减权重）';
"""

# -- 长期记忆表（MySQL 存元数据，Milvus 存向量）
CREATE_TABLE_LONG_TERM_MEMORY = """
CREATE TABLE IF NOT EXISTS long_term_memory (
    memory_id CHAR(36) PRIMARY KEY COMMENT '记忆唯一 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    memory_type VARCHAR(50) NOT NULL COMMENT '类型：preference/habit/fact/relationship/event',
    category VARCHAR(100) DEFAULT NULL COMMENT '分类',
    title VARCHAR(255) DEFAULT NULL COMMENT '记忆标题',
    content TEXT NOT NULL COMMENT '记忆内容',
    tags JSON DEFAULT NULL COMMENT '标签',
    importance_score FLOAT NOT NULL DEFAULT 0.5 COMMENT '重要性 (0-1)',
    confidence_score FLOAT NOT NULL DEFAULT 0.8 COMMENT '置信度 (0-1)',
    access_count INT NOT NULL DEFAULT 0 COMMENT '访问次数',
    source_type VARCHAR(50) DEFAULT NULL COMMENT '来源类型',
    source_uuid CHAR(36) DEFAULT NULL COMMENT '来源会话/消息 ID',
    milvus_id CHAR(36) DEFAULT NULL COMMENT 'Milvus 中的 ID（用于关联）',
    is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否启用',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    last_accessed_at TIMESTAMP DEFAULT NULL COMMENT '最后访问时间',
    
    INDEX idx_user_active (user_id, is_active),
    INDEX idx_type (memory_type),
    INDEX idx_category (category),
    INDEX idx_importance (importance_score DESC),
    INDEX idx_created_at (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='长期记忆表（MySQL+Milvus）';
"""

# =========================
# 日志与监控表
# =========================

# -- 检索日志表
CREATE_TABLE_RETRIEVAL_LOG = """
CREATE TABLE IF NOT EXISTS retrieval_log (
    retrieval_id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '检索 ID',
    session_uuid CHAR(36) NOT NULL COMMENT '会话 ID',
    message_uuid CHAR(36) NOT NULL COMMENT '消息 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    query TEXT NOT NULL COMMENT '原始问题',
    rewritten_query TEXT DEFAULT NULL COMMENT '改写后的问题',
    retrieval_strategy VARCHAR(50) DEFAULT NULL COMMENT '检索策略',
    top_k INT NOT NULL DEFAULT 10 COMMENT '请求数量',
    filter_expr TEXT DEFAULT NULL COMMENT 'Milvus 过滤表达式',
    chunks_before_filter INT DEFAULT NULL COMMENT '过滤前数量',
    chunks_after_filter INT DEFAULT NULL COMMENT '过滤后数量',
    rerank_used BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否使用重排',
    rerank_model VARCHAR(100) DEFAULT NULL COMMENT '重排模型',
    context_tokens INT DEFAULT NULL COMMENT '上下文 token 数',
    quality_score FLOAT DEFAULT NULL COMMENT '质量评分 (0-1)',
    retry_count INT NOT NULL DEFAULT 0 COMMENT '重试次数',
    total_duration_ms INT DEFAULT NULL COMMENT '总耗时',
    retrieval_duration_ms INT DEFAULT NULL COMMENT '检索耗时',
    generation_duration_ms INT DEFAULT NULL COMMENT '生成耗时',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    INDEX idx_session_created (session_uuid, created_at DESC),
    INDEX idx_message (message_uuid),
    INDEX idx_user_created (user_id, created_at),
    INDEX idx_strategy (retrieval_strategy),
    INDEX idx_quality (quality_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='检索日志表';
"""

# -- 用户反馈表
CREATE_TABLE_FEEDBACK = """
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '反馈 ID',
    message_uuid CHAR(36) NOT NULL COMMENT '消息 ID',
    session_uuid CHAR(36) NOT NULL COMMENT '会话 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    rating TINYINT(1) NOT NULL COMMENT '评分：-1=差评，0=中评，1=好评',
    feedback_type VARCHAR(50) DEFAULT NULL COMMENT '反馈类型',
    comment TEXT DEFAULT NULL COMMENT '用户评论',
    suggestion TEXT DEFAULT NULL COMMENT '改进建议',
    is_anonymous BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否匿名',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    INDEX idx_message (message_uuid),
    INDEX idx_user_created (user_id, created_at),
    INDEX idx_rating (rating),
    INDEX idx_type (feedback_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户反馈表';
"""

# -- 文档处理日志表
CREATE_TABLE_DOCUMENT_PROCESSING_LOG = """
CREATE TABLE IF NOT EXISTS document_processing_log (
    log_id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '日志 ID',
    doc_uuid CHAR(36) NOT NULL COMMENT '文档 ID',
    stage VARCHAR(50) NOT NULL COMMENT '处理阶段',
    status VARCHAR(20) NOT NULL COMMENT '状态：success/failure/running',
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
    completed_at TIMESTAMP DEFAULT NULL COMMENT '完成时间',
    duration_ms BIGINT DEFAULT NULL COMMENT '耗时 (毫秒)',
    error_message TEXT DEFAULT NULL COMMENT '错误信息',
    metadata JSON DEFAULT NULL COMMENT '阶段元数据',
    
    INDEX idx_doc (doc_uuid, started_at DESC),
    INDEX idx_stage_status (stage, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文档处理日志表';
"""

# =========================
# 系统配置表
# =========================

# -- Prompt 模板表
CREATE_TABLE_PROMPT_TEMPLATE = """
CREATE TABLE IF NOT EXISTS prompt_template (
    template_id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '模板 ID',
    name VARCHAR(100) NOT NULL COMMENT '模板名称',
    template_type VARCHAR(50) NOT NULL COMMENT '类型：qa/retrieval/summary/evaluation',
    template TEXT NOT NULL COMMENT 'Prompt 模板内容',
    version VARCHAR(20) NOT NULL DEFAULT '1.0' COMMENT '版本号',
    is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否启用',
    created_by VARCHAR(100) DEFAULT NULL COMMENT '创建者',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    UNIQUE KEY uk_name_version (name, version),
    INDEX idx_type (template_type, is_active),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Prompt 模板表';
"""

# -- 系统配置表
CREATE_TABLE_SYSTEM_CONFIG = """
CREATE TABLE IF NOT EXISTS system_config (
    config_key VARCHAR(100) PRIMARY KEY COMMENT '配置键',
    config_value TEXT NOT NULL COMMENT '配置值 (JSON 格式)',
    category VARCHAR(50) DEFAULT NULL COMMENT '配置分类',
    description VARCHAR(500) DEFAULT NULL COMMENT '配置说明',
    is_public BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否公开',
    updated_by VARCHAR(100) DEFAULT NULL COMMENT '最后修改人',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    INDEX idx_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统配置表';
"""

# =========================
# 默认数据
# =========================

# -- 默认 Prompt 模板
INSERT_DEFAULT_PROMPT_TEMPLATES = """
INSERT IGNORE INTO prompt_template (name, template_type, template, version) VALUES
('default_qa', 'qa', 
'你是一个智能助手，基于以下上下文回答问题。\n\n上下文:\n{context}\n\n问题：{question}\n\n请根据上下文提供准确、简洁的回答。',
'1.0'),

('default_retrieval', 'retrieval',
'你是一个检索助手，请分析用户问题，提取关键词和意图。\n\n用户问题：{question}\n\n请返回优化后的检索查询。',
'1.0'),

('default_summary', 'summary',
'请总结以下内容:\n\n{content}\n\n用简洁的语言概括要点。',
'1.0');
"""

# -- 默认系统配置
INSERT_DEFAULT_SYSTEM_CONFIG = """
INSERT IGNORE INTO system_config (config_key, config_value, category, description) VALUES
('default_llm_model', '{"model": "qwen-turbo", "temperature": 0.7}', 'llm', '默认 LLM 模型配置'),
('default_top_k', '{"value": 10}', 'system', '默认检索数量'),
('default_embedding_model', '{"model": "text-embedding-3-small", "dimension": 1536}', 'embedding', '默认 embedding 模型'),
('session_retention_days', '{"value": 90}', 'system', '会话数据保留天数'),
('log_retention_days', '{"value": 180}', 'system', '日志数据保留天数'),
('memory_time_decay_factor', '{"value": 0.95}', 'system', '记忆时间衰减因子（每天）');
"""

# =========================
# 所有 DDL 语句集合
# =========================

ALL_DDL_STATEMENTS = [
    # 设置字符集
    "SET NAMES utf8mb4",
    "SET CHARACTER SET utf8mb4",
    
    # 核心业务表
    CREATE_TABLE_USER,
    CREATE_TABLE_SESSION,
    CREATE_TABLE_MESSAGE,
    
    # 知识库与文档表
    CREATE_TABLE_KNOWLEDGE_BASE,
    CREATE_TABLE_DOCUMENT,
    CREATE_TABLE_CHUNK,
    
    # 记忆系统表
    CREATE_TABLE_SHORT_TERM_MEMORY,
    CREATE_TABLE_LONG_TERM_MEMORY,
    
    # 日志与监控表
    CREATE_TABLE_RETRIEVAL_LOG,
    CREATE_TABLE_FEEDBACK,
    CREATE_TABLE_DOCUMENT_PROCESSING_LOG,
    
    # 系统配置表
    CREATE_TABLE_PROMPT_TEMPLATE,
    CREATE_TABLE_SYSTEM_CONFIG,
    
    # 默认数据
    INSERT_DEFAULT_PROMPT_TEMPLATES,
    INSERT_DEFAULT_SYSTEM_CONFIG,
]
