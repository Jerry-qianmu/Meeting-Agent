# -*- coding: utf-8 -*-
"""
Repository 基类
所有 Repository 继承此类，复用 MysqlClient 的参数化查询

重要说明：
- 所有 ID 字段使用 CHAR(36) UUID 字符串格式
- 生成方式：str(uuid.uuid4())
- 不要使用 bytes 或 hex 格式
"""

from typing import Optional, Dict, Any, List
import logging

from database.mysql.mysql_client import MysqlClient
from database.mysql.repository.soft_delete_mixin import SoftDeleteMixin

logger = logging.getLogger(__name__)


class BaseRepository(SoftDeleteMixin):
    """Repository 基类，提供通用的 CRUD 操作"""
    
    def __init__(self, db_client: MysqlClient):
        """
        初始化 Repository
        
        Args:
            db_client: MysqlClient 实例
        """
        self.db = db_client
        self.table_name = self.__class__.__name__.replace('Repository', '').lower()
    
    # ==================== 通用 CRUD 方法 ====================
    
    def insert(self, data: Dict[str, Any]) -> int:
        """插入单条记录"""
        fields = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        sql = f"INSERT INTO {self.table_name} ({fields}) VALUES ({placeholders})"
        params = tuple(data.values())
        
        logger.debug(f"INSERT {self.table_name}: {sql}")
        return self.execute(sql, params)
    
    def insert_batch(self, data_list: List[Dict[str, Any]]) -> int:
        """批量插入记录"""
        if not data_list:
            return 0
        
        fields = ', '.join(data_list[0].keys())
        placeholders = ', '.join(['%s'] * len(data_list[0]))
        values_clause = ', '.join(['({})'.format(placeholders)] * len(data_list))
        sql = f"INSERT INTO {self.table_name} ({fields}) VALUES {values_clause}"
        
        params = []
        for data in data_list:
            params.extend(data.values())
        
        logger.debug(f"INSERT BATCH {self.table_name}: {len(data_list)} rows")
        return self.execute(sql, tuple(params))
    
    def update(self, conditions: Dict[str, Any], data: Dict[str, Any]) -> int:
        """更新记录"""
        set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
        where_clause = ' AND '.join([f"{k} = %s" for k in conditions.keys()])
        sql = f"UPDATE {self.table_name} SET {set_clause} WHERE {where_clause}"
        
        params = tuple(data.values()) + tuple(conditions.values())
        
        logger.debug(f"UPDATE {self.table_name}: {sql}")
        return self.execute(sql, params)
    
    def delete(self, conditions: Dict[str, Any]) -> int:
        """物理删除记录（慎用）"""
        where_clause = ' AND '.join([f"{k} = %s" for k in conditions.keys()])
        sql = f"DELETE FROM {self.table_name} WHERE {where_clause}"
        params = tuple(conditions.values())
        
        logger.debug(f"DELETE {self.table_name}: {sql}")
        return self.execute(sql, params)
    
    def find_one(self, conditions: Dict[str, Any], fields: str = '*', 
                 exclude_deleted: bool = True) -> Optional[Dict[str, Any]]:
        """查询单条记录"""
        if exclude_deleted:
            conditions['deleted_at'] = None
        
        # 构建 WHERE 子句，特殊处理 None 值（生成 IS NULL 而不是 = NULL）
        where_clauses = []
        params = []
        for key, value in conditions.items():
            if value is None:
                where_clauses.append(f"{key} IS NULL")
            else:
                where_clauses.append(f"{key} = %s")
                params.append(value)
        
        sql = f"SELECT {fields} FROM {self.table_name} WHERE {' AND '.join(where_clauses)}"
        
        logger.debug(f"SELECT ONE {self.table_name}: {sql}")
        return self.fetch_one(sql, tuple(params) if params else None)
    
    def find_by(self, 
                conditions: Dict[str, Any] = None,
                fields: str = '*',
                order_by: str = None,
                limit: int = None,
                offset: int = None,
                exclude_deleted: bool = True) -> List[Dict[str, Any]]:
        """条件查询"""
        if conditions is None:
            conditions = {}
        
        if exclude_deleted:
            conditions['deleted_at'] = None
        
        sql = f"SELECT {fields} FROM {self.table_name}"
        params = []
        
        if conditions:
            # 构建 WHERE 子句，特殊处理 None 值（生成 IS NULL 而不是 = NULL）
            where_clauses = []
            for key, value in conditions.items():
                if value is None:
                    where_clauses.append(f"{key} IS NULL")
                else:
                    where_clauses.append(f"{key} = %s")
                    params.append(value)
            sql += f" WHERE {' AND '.join(where_clauses)}"
        
        if order_by:
            sql += f" ORDER BY {order_by}"
        
        if limit:
            sql += f" LIMIT {limit}"
            if offset:
                sql += f" OFFSET {offset}"
        
        logger.debug(f"SELECT BY {self.table_name}: {sql}")
        return self.fetch_all(sql, tuple(params) if params else None)
    
    def find_all(self, fields: str = '*', order_by: str = None, 
                 limit: int = None, exclude_deleted: bool = True) -> List[Dict[str, Any]]:
        """查询所有记录"""
        if exclude_deleted:
            return self.find_by({}, fields, order_by, limit, exclude_deleted=True)
        
        sql = f"SELECT {fields} FROM {self.table_name}"
        
        if order_by:
            sql += f" ORDER BY {order_by}"
        
        if limit:
            sql += f" LIMIT {limit}"
        
        logger.debug(f"SELECT ALL {self.table_name}: {sql}")
        return self.fetch_all(sql)
    
    def count(self, conditions: Dict[str, Any] = None, exclude_deleted: bool = True) -> int:
        """统计记录数"""
        if conditions is None:
            conditions = {}
        
        if exclude_deleted:
            conditions['deleted_at'] = None
        
        sql = f"SELECT COUNT(*) as count FROM {self.table_name}"
        params = []
        
        if conditions:
            # 构建 WHERE 子句，特殊处理 None 值（生成 IS NULL 而不是 = NULL）
            where_clauses = []
            for key, value in conditions.items():
                if value is None:
                    where_clauses.append(f"{key} IS NULL")
                else:
                    where_clauses.append(f"{key} = %s")
                    params.append(value)
            sql += f" WHERE {' AND '.join(where_clauses)}"
        
        logger.debug(f"COUNT {self.table_name}: {sql}")
        result = self.fetch_one(sql, tuple(params) if params else None)
        return result['count'] if result else 0
    
    # ==================== 底层方法 ====================
    
    def execute(self, sql: str, params: tuple = None) -> int:
        """执行 SQL 语句"""
        try:
            return self.db.execute(sql, params)
        except Exception as e:
            logger.error(f"Execute failed: {sql} - {str(e)}")
            raise
    
    def fetch_all(self, sql: str, params: tuple = None) -> List[Dict[str, Any]]:
        """查询多条记录"""
        try:
            return self.db.query_all(sql, params)
        except Exception as e:
            logger.error(f"Fetch all failed: {sql} - {str(e)}")
            raise
    
    def fetch_one(self, sql: str, params: tuple = None) -> Optional[Dict[str, Any]]:
        """查询单条记录"""
        try:
            return self.db.query_one(sql, params)
        except Exception as e:
            logger.error(f"Fetch one failed: {sql} - {str(e)}")
            raise
