-- 修复 short_term_memory 表结构
-- 添加 deleted_at 字段以支持软删除

-- 1. 添加 deleted_at 字段
ALTER TABLE short_term_memory 
ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL COMMENT '软删除时间 (NULL=未删除)' AFTER created_at;

-- 2. 添加索引
ALTER TABLE short_term_memory 
ADD INDEX idx_deleted_at (deleted_at);

-- 验证修改
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT 
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_SCHEMA = 'knowledge_base_db' 
  AND TABLE_NAME = 'short_term_memory'
ORDER BY ORDINAL_POSITION;
