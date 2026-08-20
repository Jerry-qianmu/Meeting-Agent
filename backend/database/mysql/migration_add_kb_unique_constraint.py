# -*- coding: utf-8 -*-
"""
数据库迁移脚本：添加知识库名称唯一约束
"""
import sys
import os

cur_dir = os.path.dirname(__file__)
sys.path.insert(0, cur_dir)

from mysql_client import MysqlClient
from config.settings import Settings


def add_unique_constraint():
    """添加知识库名称唯一约束"""
    settings = Settings()
    
    # 创建数据库连接
    db_client = MysqlClient(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset='utf8mb4'
    )
    
    try:
        # 检查约束是否已存在
        result = db_client.query_one("""
            SELECT COUNT(*) as count 
            FROM information_schema.TABLE_CONSTRAINTS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'knowledge_base' 
            AND CONSTRAINT_NAME = 'uk_user_name'
        """, (settings.mysql_database,))
        
        if result and result['count'] > 0:
            print("✅ 唯一约束 uk_user_name 已存在")
            return
        
        # 添加唯一约束
        print("📦 正在添加知识库名称唯一约束...")
        db_client.execute("""
            ALTER TABLE knowledge_base 
            ADD UNIQUE KEY uk_user_name (user_id, name, deleted_at)
            COMMENT '同一用户下知识库名称唯一（软删除时允许重名）'
        """)
        print("✅ 唯一约束添加成功")
        
        # 验证
        result = db_client.query_one("""
            SELECT COUNT(*) as count 
            FROM information_schema.TABLE_CONSTRAINTS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'knowledge_base' 
            AND CONSTRAINT_NAME = 'uk_user_name'
        """, (settings.mysql_database,))
        
        if result and result['count'] > 0:
            print("✅ 验证通过：唯一约束已生效")
        else:
            print("❌ 验证失败：唯一约束未找到")
            
    except Exception as e:
        print(f"❌ 添加唯一约束失败：{e}")
        raise
    finally:
        db_client.close()


if __name__ == "__main__":
    add_unique_constraint()
    print("\n✅ 数据库迁移完成")
