# -*- coding: utf-8 -*-
"""
数据库初始化脚本
"""
import sys
import os

cur_dir = os.path.dirname(__file__)
sys.path.insert(0, cur_dir)

from database_schema import ALL_DDL_STATEMENTS
from mysql_client import MysqlClient
from config.settings import Settings


class DatabaseInitializer:
    """数据库初始化器"""
    
    def __init__(self, mysql_client: MysqlClient):
        self.client = mysql_client
    
    def initialize_database(self, drop_existing: bool = False) -> bool:
        """
        初始化数据库
        
        Args:
            drop_existing: 是否删除现有表（危险操作！）
            
        Returns:
            bool: 是否成功
        """
        try:
            if drop_existing:
                print("⚠️  正在删除现有表...")
                self._drop_all_tables()
            
            print("📦 正在创建数据库表...")
            for ddl in ALL_DDL_STATEMENTS:
                ddl = ddl.strip()
                if ddl and not ddl.startswith("--"):
                    try:
                        self.client.execute(ddl)
                    except Exception as e:
                        # 忽略唯一约束已存在的错误
                        if "Duplicate key name" in str(e):
                            print(f"  ⚠️  跳过已存在的索引：{ddl[:50]}...")
                            continue
                        raise
            
            # 添加知识库名称唯一约束（如果不存在）
            print("🔧 添加知识库名称唯一约束...")
            try:
                # 检查约束是否已存在
                result = self.client.query_one("""
                    SELECT COUNT(*) as count 
                    FROM information_schema.TABLE_CONSTRAINTS 
                    WHERE TABLE_SCHEMA = DATABASE() 
                    AND TABLE_NAME = 'knowledge_base' 
                    AND CONSTRAINT_NAME = 'uk_user_name'
                """)
                
                if result and result.get('count', 0) == 0:
                    # 约束不存在，添加它
                    self.client.execute("""
                        ALTER TABLE knowledge_base 
                        ADD UNIQUE KEY uk_user_name (user_id, name, deleted_at)
                    """)
                    print("  ✅ 唯一约束添加成功")
                else:
                    print("  ✅ 唯一约束已存在")
            except Exception as e:
                print(f"  ⚠️  添加唯一约束时出错：{e}")
            
            print("✅ 数据库初始化完成")
            return True
            
        except Exception as e:
            print(f"❌ 数据库初始化失败：{e}")
            return False
    
    def _drop_all_tables(self):
        """删除所有表（按依赖顺序）"""
        tables = [
            'retrieval_result',  # 如果存在
            'document_processing_log',
            'feedback',
            'retrieval_log',
            'long_term_memory',
            'short_term_memory',
            'chunk',
            'document',
            'knowledge_base',
            'message',
            'session',
            'prompt_template',
            'system_config',
            'user',
        ]
        
        for table in tables:
            try:
                self.client.execute(f"DROP TABLE IF EXISTS {table}")
                print(f"  - 删除表：{table}")
            except Exception as e:
                print(f"  - 警告：删除 {table} 失败 - {e}")
    
    def verify_tables(self) -> dict:
        """验证表是否创建成功"""
        tables = [
            'user', 'session', 'message',
            'knowledge_base', 'document', 'chunk',
            'short_term_memory', 'long_term_memory',
            'retrieval_log', 'feedback',
            'document_processing_log',
            'prompt_template', 'system_config'
        ]
        
        results = {}
        for table in tables:
            try:
                result = self.client.query_one(
                    "SELECT COUNT(*) as count FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name = %s",
                    (table,)
                )
                results[table] = result['count'] > 0 if result else False
            except Exception as e:
                results[table] = False
                print(f"  - 验证 {table} 失败：{e}")
        
        return results


def initialize_tables(mysql_client: MysqlClient) -> bool:
    """
    便捷函数：初始化数据库表
    
    Args:
        mysql_client: MysqlClient 实例
        
    Returns:
        bool: 是否成功
    """
    initializer = DatabaseInitializer(mysql_client)
    return initializer.initialize_database()


def initialize_database():
    """
    全局初始化函数：用于从外部调用
    会创建临时的 MySQL 客户端来初始化数据库
    """
    from mysql_client import get_db_client
    
    mysql_client = get_db_client()
    if not mysql_client:
        raise RuntimeError("MySQL 客户端未初始化")
    
    initializer = DatabaseInitializer(mysql_client)
    return initializer.initialize_database()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='初始化 MySQL 数据库')
    parser.add_argument('--drop', action='store_true', help='删除现有表后重新创建（危险！）')
    args = parser.parse_args()
    
    settings = Settings()
    mysql_client = MysqlClient(settings)
    
    initializer = DatabaseInitializer(mysql_client)
    success = initializer.initialize_database(drop_existing=args.drop)
    
    if success:
        print("\n📋 验证表创建结果:")
        verification = initializer.verify_tables()
        for table, exists in verification.items():
            status = "✅" if exists else "❌"
            print(f"  {status} {table}")
