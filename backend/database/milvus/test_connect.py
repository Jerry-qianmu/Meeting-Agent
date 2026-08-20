"""
Milvus 客户端包装
提供连接管理和健康检查
"""

import logging
import sys
import os

from pymilvus import MilvusClient

logger = logging.getLogger(__name__)

cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.insert(0, os.path.dirname(parent_dir))

from config.settings import Settings
from milvus_client import get_milvus_client

client = get_milvus_client()
