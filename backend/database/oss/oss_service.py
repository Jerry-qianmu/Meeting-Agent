# -*- coding: utf-8 -*-
"""
阿里云 OSS 服务
负责文件上传、下载、删除和临时 URL 生成
"""

import logging
import datetime
from typing import Optional, List
import urllib3
import alibabacloud_oss_v2 as oss

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import os
import sys

cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.insert(0, parent_dir)

from config.settings import Settings

settings = Settings()
logger = logging.getLogger(__name__)


class OSSService:
    """阿里云 OSS 服务"""

    def __init__(self):
        """初始化 OSS 客户端"""
        credentials_provider = oss.credentials.StaticCredentialsProvider(
            access_key_id=settings.oss_access_key_id,
            access_key_secret=settings.oss_access_key_secret,
        )
        cfg = oss.config.load_default()
        cfg.credentials_provider = credentials_provider
        cfg.region = settings.oss_region
        cfg.endpoint = settings.oss_endpoint
        cfg.insecure_skip_verify = True
        self.client = oss.Client(cfg)
        self.bucket = settings.oss_bucket
        logger.info(f"OSS 服务初始化成功：bucket={self.bucket}, region={settings.oss_region}")

    # ==================== 上传 ====================

    def upload_bytes(self, object_key: str, file_content: bytes) -> str:
        """
        直接用完整 object_key 上传文件（适用于 document_service 等场景）

        Args:
            object_key: 完整 OSS 路径，如 kb/my_kb_123/document/file.pdf
            file_content: 文件二进制内容

        Returns:
            str: object_key（上传成功返回原路径）

        Raises:
            Exception: 上传失败时抛出异常
        """
        try:
            result = self.client.put_object(
                oss.PutObjectRequest(
                    bucket=self.bucket,
                    key=object_key,
                    body=file_content,
                )
            )
            logger.info(f"[OSS] 上传成功：{object_key}, status={result.status_code}")
            return object_key
        except Exception as e:
            logger.error(f"[OSS] 上传失败：{object_key}, error={e}")
            raise Exception(f"OSS 上传失败：{e}")

    def upload_file(self, category: str, file_name: str, file_content: bytes) -> str:
        """
        上传文件到 OSS（按类目组织）

        Args:
            category: 类目名称，作为 OSS 目录（如 'documents', 'images', 'exports'）
            file_name: 文件名
            file_content: 文件二进制内容

        Returns:
            str: object_key（格式：category/file_name）
        """
        object_key = f"{category}/{file_name}"
        return self.upload_bytes(object_key, file_content)

    def upload_document(self, kb_id: str, doc_id: str, file_content: bytes,
                        original_filename: str) -> str:
        """
        上传原始文档到 OSS

        Args:
            kb_id: 知识库 ID
            doc_id: 文档 ID
            file_content: 文件内容
            original_filename: 原始文件名

        Returns:
            str: object_key
        """
        object_key = f"documents/{kb_id}/{doc_id}/{original_filename}"
        return self.upload_bytes(object_key, file_content)

    def upload_processed_file(self, category: str, kb_id: str, doc_id: str,
                              file_name: str, file_content: bytes) -> str:
        """
        上传处理后的中间文件（如切片文本、提取的元数据等）

        Args:
            category: 处理类型（如 'chunks', 'metadata', 'extracted'）
            kb_id: 知识库 ID
            doc_id: 文档 ID
            file_name: 文件名
            file_content: 文件内容

        Returns:
            str: object_key
        """
        object_key = f"{category}/{kb_id}/{doc_id}/{file_name}"
        return self.upload_bytes(object_key, file_content)

    # ==================== 下载 ====================

    def get_object_bytes(self, object_key: str) -> bytes:
        """
        从 OSS 下载对象，返回字节内容

        Args:
            object_key: OSS 对象路径

        Returns:
            bytes: 文件内容

        Raises:
            Exception: 下载失败时抛出异常
        """
        try:
            result = self.client.get_object(
                oss.GetObjectRequest(bucket=self.bucket, key=object_key)
            )
            with result.body as body:
                data = body.read()
            logger.info(f"[OSS] 下载成功：{object_key}, size={len(data)}")
            return data
        except Exception as e:
            logger.error(f"[OSS] 下载失败：{object_key}, error={e}")
            raise Exception(f"OSS 下载失败：{e}")

    def get_document(self, kb_id: str, doc_id: str, original_filename: str) -> bytes:
        """
        下载原始文档

        Args:
            kb_id: 知识库 ID
            doc_id: 文档 ID
            original_filename: 原始文件名

        Returns:
            bytes: 文件内容
        """
        object_key = f"documents/{kb_id}/{doc_id}/{original_filename}"
        return self.get_object_bytes(object_key)

    # ==================== 删除 ====================

    def delete_objects(self, object_keys: List[str]) -> int:
        """
        批量删除 OSS 对象，返回实际删除数量

        Args:
            object_keys: OSS 对象路径列表

        Returns:
            int: 成功删除的数量
        """
        if not object_keys:
            return 0

        try:
            objects = [oss.DeleteObject(key=k) for k in object_keys]
            result = self.client.delete_multiple_objects(
                oss.DeleteMultipleObjectsRequest(bucket=self.bucket, objects=objects)
            )
            # alibabacloud_oss_v2 默认非静默模式：deleted_objects 包含所有成功删除的对象
            deleted_count = len(result.deleted_objects) if result.deleted_objects else 0
            failed = len(object_keys) - deleted_count
            logger.info(f"[OSS] 批量删除：请求 {len(object_keys)} 个，成功 {deleted_count} 个，失败 {failed} 个")
            return deleted_count
        except Exception as e:
            logger.error(f"[OSS] 批量删除失败：{e}")
            return 0

    def delete_document(self, kb_id: str, doc_id: str) -> int:
        """
        删除文档的所有相关文件（原始文件 + 处理后的文件）

        Args:
            kb_id: 知识库 ID
            doc_id: 文档 ID

        Returns:
            int: 成功删除的文件数量
        """
        # 构建文档相关的 object_key 列表
        object_keys = [
            f"documents/{kb_id}/{doc_id}/",  # 这会匹配该目录下的所有文件
        ]

        # 删除原始文件和中间文件
        return self.delete_objects(object_keys)

    def delete_by_prefix(self, prefix: str) -> int:
        """
        根据前缀批量删除对象

        Args:
            prefix: OSS 对象前缀（如 'documents/kb_123/'）

        Returns:
            int: 成功删除的数量
        """
        try:
            # 先列出所有匹配的对象
            list_result = self.client.list_objects(
                oss.ListObjectsRequest(bucket=self.bucket, prefix=prefix)
            )
            
            if not list_result.contents:
                logger.info(f"[OSS] 前缀 {prefix} 下无对象可删除")
                return 0
            
            object_keys = [obj.key for obj in list_result.contents]
            return self.delete_objects(object_keys)
        except Exception as e:
            logger.error(f"[OSS] 按前缀删除失败：{prefix}, error={e}")
            return 0

    # ==================== 预签名 URL ====================

    def get_presigned_url(self, object_key: str, expires: int = 3600) -> str:
        """
        生成临时签名 URL（用于前端直接上传/下载）

        Args:
            object_key: OSS 对象路径
            expires: 有效期（秒），默认 3600（1 小时）

        Returns:
            str: 临时访问 URL

        Raises:
            Exception: 生成失败时抛出异常
        """
        try:
            result = self.client.presign(
                oss.GetObjectRequest(
                    bucket=self.bucket,
                    key=object_key,
                ),
                expires=datetime.timedelta(seconds=expires),
            )
            logger.info(f"[OSS] 生成临时 URL: {object_key}, expires={expires}s")
            return result.url
        except Exception as e:
            logger.error(f"[OSS] 生成临时 URL 失败：{object_key}, error={e}")
            raise Exception(f"生成临时 URL 失败：{e}")

    def get_presigned_url_for_upload(self, object_key: str,
                                      expires: int = 3600) -> str:
        """
        生成用于上传的预签名 URL（PUT 方法）

        Args:
            object_key: OSS 对象路径
            expires: 有效期（秒）

        Returns:
            str: 临时上传 URL
        """
        try:
            result = self.client.presign(
                oss.PutObjectRequest(
                    bucket=self.bucket,
                    key=object_key,
                ),
                expires=datetime.timedelta(seconds=expires),
            )
            logger.info(f"[OSS] 生成上传 URL: {object_key}, expires={expires}s")
            return result.url
        except Exception as e:
            logger.error(f"[OSS] 生成上传 URL 失败：{object_key}, error={e}")
            raise Exception(f"生成上传 URL 失败：{e}")

    def get_presigned_url_by_category(self, category: str, file_name: str,
                                       expires: int = 3600) -> str:
        """
        通过类目名和文件名生成临时 URL

        Args:
            category: 类目名称
            file_name: 文件名
            expires: 有效期（秒）

        Returns:
            str: 临时访问 URL
        """
        object_key = f"{category}/{file_name}"
        return self.get_presigned_url(object_key, expires)

    def get_document_presigned_url(self, kb_id: str, doc_id: str,
                                   original_filename: str,
                                   expires: int = 3600) -> str:
        """
        生成文档的临时下载 URL

        Args:
            kb_id: 知识库 ID
            doc_id: 文档 ID
            original_filename: 原始文件名
            expires: 有效期（秒）

        Returns:
            str: 临时下载 URL
        """
        object_key = f"documents/{kb_id}/{doc_id}/{original_filename}"
        return self.get_presigned_url(object_key, expires)

    # ==================== 其他工具方法 ====================

    def file_exists(self, object_key: str) -> bool:
        """
        检查 OSS 对象是否存在

        Args:
            object_key: OSS 对象路径

        Returns:
            bool: 是否存在
        """
        try:
            result = self.client.head_object(
                oss.HeadObjectRequest(bucket=self.bucket, key=object_key)
            )
            return result.status_code == 200
        except Exception:
            return False

    def get_file_size(self, object_key: str) -> Optional[int]:
        """
        获取 OSS 对象大小

        Args:
            object_key: OSS 对象路径

        Returns:
            Optional[int]: 文件大小（字节），不存在返回 None
        """
        try:
            result = self.client.head_object(
                oss.HeadObjectRequest(bucket=self.bucket, key=object_key)
            )
            if result.status_code == 200:
                return result.content_length
            return None
        except Exception as e:
            logger.warning(f"[OSS] 获取文件大小失败：{object_key}, error={e}")
            return None


# ==================== 单例模式 ====================

_instance: Optional[OSSService] = None


def get_oss_service() -> OSSService:
    """
    获取 OSS 服务单例

    Returns:
        OSSService: OSS 服务实例
    """
    global _instance
    if _instance is None:
        _instance = OSSService()
    return _instance
