# -*- coding: utf-8 -*-
"""
迁移脚本：给 chunk 表新增 description、keywords、heading_path 字段
运行方式：python -m database.mysql.migration_chunk_enrichment
"""

import os
import sys
import logging

cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grand_parent_dir)

from database.mysql.mysql_client import get_db_client

logger = logging.getLogger(__name__)

MIGRATION_SQL = [
    """
    ALTER TABLE chunk
    ADD COLUMN description TEXT DEFAULT NULL COMMENT 'chunk 摘要描述（LLM 生成）'
    AFTER token_count
    """,
    """
    ALTER TABLE chunk
    ADD COLUMN keywords JSON DEFAULT NULL COMMENT '关键词列表（LLM 生成）'
    AFTER description
    """,
    """
    ALTER TABLE chunk
    ADD COLUMN heading_path JSON DEFAULT NULL COMMENT '标题路径'
    AFTER keywords
    """,
]


def run_migration():
    """执行迁移"""
    db = get_db_client()
    if not db:
        logger.error("数据库连接失败")
        return False

    for sql in MIGRATION_SQL:
        sql = sql.strip()
        if not sql:
            continue
        try:
            db.execute(sql)
            logger.info(f"执行成功: {sql[:80]}...")
        except Exception as e:
            if "Duplicate column name" in str(e):
                logger.info(f"列已存在，跳过: {sql[:80]}...")
            else:
                logger.error(f"执行失败: {e}")
                return False

    logger.info("迁移完成")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
