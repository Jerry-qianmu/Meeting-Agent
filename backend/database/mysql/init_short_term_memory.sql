-- ========================================
-- 短期记忆系统数据库初始化脚本
-- ========================================
-- 执行方式：mysql -u root -p knowledge_base < init_short_term_memory.sql
-- ========================================

-- 设置字符集
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- ========================================
-- 1. 短期记忆表
-- ========================================

CREATE TABLE IF NOT EXISTS short_term_memory (
    memory_id CHAR(36) PRIMARY KEY COMMENT '记忆唯一 ID',
    session_uuid CHAR(36) NOT NULL COMMENT '会话 ID',
    user_id CHAR(36) NOT NULL COMMENT '用户 ID',
    query_summary VARCHAR(500) DEFAULT NULL COMMENT '问题摘要',
    answer_summary VARCHAR(1000) DEFAULT NULL COMMENT '答案摘要',
    entities JSON DEFAULT NULL COMMENT '提取的实体 {"person": [...], "organization": [...]}',
    key_facts JSON DEFAULT NULL COMMENT '关键事实列表 [{"fact": "...", "type": "..."}]',
    message_uuid CHAR(36) DEFAULT NULL COMMENT '关联的消息 ID',
    base_relevance_score FLOAT NOT NULL DEFAULT 1.0 COMMENT '基础相关性分数 (0-1)',
    access_count INT NOT NULL DEFAULT 1 COMMENT '访问次数',
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '最后访问时间',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    INDEX idx_session (session_uuid, created_at DESC),
    INDEX idx_user (user_id),
    INDEX idx_last_accessed (last_accessed_at DESC),
    INDEX idx_base_relevance (base_relevance_score DESC),
    INDEX idx_created_at (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短期记忆表（长期存储，时间衰减权重）';

-- ========================================
-- 2. 测试数据
-- ========================================

-- 插入测试记忆数据
INSERT INTO short_term_memory (
    memory_id, session_uuid, user_id, query_summary, answer_summary, 
    entities, key_facts, message_uuid, base_relevance_score, access_count,
    created_at, last_accessed_at
) VALUES
(
    'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    '550e8400-e29b-41d4-a716-446655440000',
    'user_001',
    '什么是机器学习？',
    '机器学习是人工智能的一个子领域，使用算法从数据中学习模式...',
    '{"concept": ["机器学习", "人工智能", "数据科学"]}',
    '[{"fact": "机器学习是 AI 的子领域", "type": "definition"}]',
    'msg-001',
    0.85,
    3,
    '2026-05-01 10:00:00',
    '2026-05-02 14:30:00'
),
(
    'b2c3d4e5-f6a7-8901-bcde-f12345678901',
    '550e8400-e29b-41d4-a716-446655440000',
    'user_001',
    '学习机器学习需要哪些基础知识？',
    '需要掌握 Python 编程、线性代数、概率统计、微积分等基础知识...',
    '{"skill": ["Python", "线性代数", "概率统计"], "topic": ["机器学习"]}',
    '[{"fact": "Python 是机器学习最常用的编程语言", "type": "recommendation"}]',
    'msg-002',
    0.75,
    2,
    '2026-05-01 11:00:00',
    '2026-05-02 15:00:00'
),
(
    'c3d4e5f6-a7b8-9012-cdef-123456789012',
    '550e8400-e29b-41d4-a716-446655440000',
    'user_001',
    '机器学习有哪些应用场景？',
    '机器学习的典型应用场景包括：图像识别、自然语言处理、推荐系统、欺诈检测等...',
    '{"application": ["图像识别", "自然语言处理", "推荐系统"]}',
    '[{"fact": "推荐系统广泛使用协同过滤算法", "type": "example"}]',
    'msg-003',
    0.80,
    1,
    '2026-05-01 14:00:00',
    '2026-05-01 14:00:00'
),
(
    'd4e5f6a7-b8c9-0123-def0-234567890123',
    '550e8400-e29b-41d4-a716-446655440000',
    'user_001',
    '什么是深度学习？',
    '深度学习是机器学习的一个分支，使用多层神经网络进行特征学习和模式识别...',
    '{"concept": ["深度学习", "神经网络", "机器学习"]}',
    '[{"fact": "深度学习使用多层神经网络", "type": "definition"}]',
    'msg-004',
    0.70,
    1,
    '2026-04-28 09:00:00',
    '2026-04-28 09:00:00'
),
(
    'e5f6a7b8-c9d0-1234-ef01-345678901234',
    '550e8400-e29b-41d4-a716-446655440000',
    'user_001',
    'Python 有哪些机器学习库？',
    '常用的 Python 机器学习库包括：scikit-learn、TensorFlow、PyTorch、Keras、XGBoost 等...',
    '{"library": ["scikit-learn", "TensorFlow", "PyTorch", "Keras"]}',
    '[{"fact": "scikit-learn 适合传统机器学习算法", "type": "recommendation"}]',
    'msg-005',
    0.65,
    4,
    '2026-04-25 16:00:00',
    '2026-05-03 10:00:00'
);

-- ========================================
-- 3. 验证数据
-- ========================================

-- 查询所有测试数据
SELECT 
    memory_id,
    query_summary,
    base_relevance_score,
    access_count,
    created_at,
    last_accessed_at
FROM short_term_memory
WHERE user_id = 'user_001'
ORDER BY created_at DESC;

-- ========================================
-- 4. 统计信息
-- ========================================

-- 获取用户的记忆统计
SELECT 
    user_id,
    COUNT(*) as total_memories,
    AVG(base_relevance_score) as avg_relevance,
    SUM(access_count) as total_accesses,
    MAX(created_at) as latest_memory
FROM short_term_memory
GROUP BY user_id;

-- ========================================
-- 5. 查询示例
-- ========================================

-- 查询最近 10 条记忆
SELECT * FROM short_term_memory
WHERE user_id = 'user_001'
ORDER BY created_at DESC
LIMIT 10;

-- 查询访问次数最多的记忆
SELECT * FROM short_term_memory
WHERE user_id = 'user_001'
ORDER BY access_count DESC
LIMIT 10;

-- 查询高相关性的记忆
SELECT * FROM short_term_memory
WHERE user_id = 'user_001' AND base_relevance_score >= 0.7
ORDER BY base_relevance_score DESC;

-- ========================================
-- 脚本结束
-- ========================================
