# -*- coding: utf-8 -*-
"""
MySQL 连接池
提供参数化查询，彻底避免 SQL 注入
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date
import uuid as uuid_module

import pymysql
from pymysql.cursors import DictCursor
from sqlalchemy.engine import Engine
from sqlalchemy import create_engine, text  # 创建 mysql 连接池

"""添加 import 路径导入 config"""
import os
import sys
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.insert(0, os.path.dirname(parent_dir))

from config.settings import Settings

logger = logging.getLogger(__name__)


class MysqlClient:

    def __init__(self, settings: Settings):
        self.settings = settings
        self.host = self.settings.mysql_host
        self.port = self.settings.mysql_port
        self.db = self.settings.mysql_db
        self.user = self.settings.mysql_user
        self.password = self.settings.mysql_password

        self.engine: Engine = self._create_engine()
        print(self.user, self.password)

    def _create_engine(self) -> Engine:
        """创建 mysql 连接池"""
        url = (
        f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}?charset=utf8mb4"
    )
        _engine = create_engine(url,
                pool_size=10,  # 常驻连接上限
                max_overflow=20,  # 临时连接上限
                pool_recycle=3600,  # 连接最大存活时间，超出该时间则断开连接
                pool_timeout=30,  # 连接池中连接最大等待时间，当连接用完时最多等待时间
                pool_pre_ping=True,  # 连接健康检查
                echo=False,
                )
        logger.info(f"创建 mysql 连接池成功:{_engine}")
        return _engine
    
   # ---------------- 辅助函数：数据转换 ----------------
    def _convert_row_to_dict(self, row) -> Dict[str, Any]:
        """
        将数据库行转换为可 JSON 序列化的字典
        处理特殊类型（datetime 等）
        
        注意：UUID 字段使用 CHAR(36) 存储，直接返回字符串，无需转换
        """
        result = {}
        for key, value in row._mapping.items():
            if isinstance(value, (datetime, date)):
                # 日期时间转换为 ISO 格式字符串
                result[key] = value.isoformat()
            elif hasattr(value, '__dict__'):
                # 其他对象转换为字典
                result[key] = dict(value)
            else:
                # 直接返回（包括 CHAR(36) UUID 字符串）
                result[key] = value
        return result

    # ---------------- 查询 ----------------
    def query_all(self, sql: str, params: tuple = None):
        with self.engine.connect() as conn:
            # 设置事务隔离级别为 READ_COMMITTED，确保能看到已提交的更改
            conn.execute(text("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED"))
            conn.commit()
            # 将 tuple 转换为 dict 以配合 SQLAlchemy 的命名参数
            if params:
                # 使用 positional parameters 通过 dict 格式
                param_dict = {f"param_{i}": v for i, v in enumerate(params)}
                # 重新替换 SQL 中的 %s 为 :param_i 格式
                for i in range(len(params)):
                    sql = sql.replace('%s', f':param_{i}', 1)
                result = conn.execute(text(sql), param_dict)
            else:
                result = conn.execute(text(sql))
            conn.commit()
            # 转换所有行，确保可 JSON 序列化
            return [self._convert_row_to_dict(row) for row in result]

    def query_one(self, sql: str, params: tuple = None):
        with self.engine.connect() as conn:
            # 设置事务隔离级别为 READ_COMMITTED，确保能看到已提交的更改
            conn.execute(text("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED"))
            conn.commit()
            if params:
                param_dict = {f"param_{i}": v for i, v in enumerate(params)}
                for i in range(len(params)):
                    sql = sql.replace('%s', f':param_{i}', 1)
                result = conn.execute(text(sql), param_dict)
            else:
                result = conn.execute(text(sql))
            row = result.fetchone()
            conn.commit()
            return self._convert_row_to_dict(row) if row else None

    # ---------------- 新增 / 修改 / 删除 ----------------
    def execute(self, sql: str, params: tuple = None):
        with self.engine.connect() as conn:  # 使用 connect 而不是 begin
            if params:
                param_dict = {f"param_{i}": v for i, v in enumerate(params)}
                for i in range(len(params)):
                    sql = sql.replace('%s', f':param_{i}', 1)
                result = conn.execute(text(sql), param_dict)
            else:
                result = conn.execute(text(sql))
            conn.commit()  # 手动提交
            return result.rowcount  # 影响行数
        
    def check_connection(self) -> bool:
        """检查 MySQL 连接是否可用"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.debug("MySQL 连接正常")
                return True
        except Exception as e:
            logger.warning(f"MySQL 连接检查失败：{e}")
            return False
    
    def _close(self):
        if self.engine:
            self.engine.dispose()
            logger.info("关闭 mysql 连接池成功")


# ── 全局单例管理 ───────────────────────────────────────────────────────────

_mysql_client_instance: Optional[MysqlClient] = None


def init_mysql_pool(settings: Settings) -> None:
    """
    初始化 MySQL 连接池（单例）
    
    Args:
        settings: 数据库配置
    """
    global _mysql_client_instance
    if _mysql_client_instance is None:
        _mysql_client_instance = MysqlClient(settings)
        logger.info("MySQL 连接池初始化成功")


def get_db_client() -> MysqlClient:
    """
    获取 MySQL 客户端实例（单例模式）
    
    Returns:
        MysqlClient: MySQL 客户端实例
        
    Raises:
        RuntimeError: 如果 MySQL 客户端未初始化
    """
    global _mysql_client_instance
    if _mysql_client_instance is None:
        raise RuntimeError("MySQL 客户端未初始化，请先调用 init_mysql_pool()")
    return _mysql_client_instance


def close_mysql_pool() -> None:
    """关闭 MySQL 连接池"""
    global _mysql_client_instance
    if _mysql_client_instance is not None:
        _mysql_client_instance._close()
        _mysql_client_instance = None
        logger.info("MySQL 连接池已关闭")
