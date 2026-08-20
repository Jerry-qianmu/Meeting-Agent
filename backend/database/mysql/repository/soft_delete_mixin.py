# -*- coding: utf-8 -*-
"""
软删除 Mixin 类
为 Repository 提供软删除功能
"""
from typing import Dict, Any, Optional, List


class SoftDeleteMixin:
    """软删除混入类"""
    
    def soft_delete(self, conditions: Dict[str, Any]) -> int:
        """
        软删除记录
        
        Args:
            conditions: 条件字典 {field: value}
            
        Returns:
            int: 影响的行数
        """
        where_clause = ' AND '.join([f"{k} = %s" for k in conditions.keys()])
        sql = f"UPDATE {self.table_name} SET deleted_at = CURRENT_TIMESTAMP WHERE {where_clause}"
        params = tuple(conditions.values())
        
        return self.execute(sql, params)
    
    def find_by(self, 
                conditions: Dict[str, Any] = None,
                fields: str = '*',
                order_by: str = None,
                limit: int = None,
                offset: int = None,
                exclude_deleted: bool = True) -> List[Dict[str, Any]]:
        """
        条件查询（默认排除软删除的数据）
        
        Args:
            conditions: 条件字典
            fields: 查询字段
            order_by: 排序字段
            limit: 限制数量
            offset: 偏移量
            exclude_deleted: 是否排除软删除的数据
            
        Returns:
            List[Dict]: 记录列表
        """
        if conditions is None:
            conditions = {}
        
        # 默认排除软删除的数据
        if exclude_deleted:
            conditions['deleted_at'] = None
        
        return super().find_by(conditions, fields, order_by, limit, offset)
    
    def find_all(self, fields: str = '*', order_by: str = None, 
                 limit: int = None, exclude_deleted: bool = True) -> List[Dict[str, Any]]:
        """
        查询所有记录（默认排除软删除的数据）
        
        Args:
            fields: 查询字段
            order_by: 排序字段
            limit: 限制数量
            exclude_deleted: 是否排除软删除的数据
            
        Returns:
            List[Dict]: 记录列表
        """
        if exclude_deleted:
            return self.find_by({}, fields, order_by, limit, exclude_deleted=True)
        
        return super().find_all(fields, order_by, limit)
