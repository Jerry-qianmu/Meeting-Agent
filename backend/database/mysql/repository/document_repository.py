# -*- coding: utf-8 -*-
"""
Document 数据访问层
"""

from typing import Optional, Dict, Any, List
import logging
import sys
import os
import uuid
import json

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grand_parent_dir)

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class DocumentRepository(BaseRepository):
    """文档表 Repository"""
    
    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'document'
    
    # ==================== 文档创建 ====================
    
    def create_document(self, kb_id: str, user_id: str,
                        original_filename: str, file_extension: str,
                        file_size: int, oss_path: str,
                        title: str = None, oss_bucket: str = None,
                        metadata: dict = None) -> Dict[str, Any]:
        """
        创建文档记录
        
        Args:
            kb_id: 知识库 ID
            user_id: 用户 ID
            original_filename: 原始文件名
            file_extension: 文件扩展名
            file_size: 文件大小
            oss_path: OSS 路径
            title: 文档标题
            oss_bucket: OSS 桶名
            metadata: 扩展元数据
            
        Returns:
            Dict: 创建的文档数据
        """
        doc_id = str(uuid.uuid4())
        data = {
            'doc_uuid': doc_id,
            'kb_uuid': kb_id,
            'user_id': user_id,
            'title': title,
            'original_filename': original_filename,
            'file_extension': file_extension,
            'file_size': file_size,
            'oss_path': oss_path,
            'oss_bucket': oss_bucket,
            'chunk_count': 0,
            'total_tokens': 0,
            'status': 0,  # pending
            'version': 1,
            'metadata': json.dumps(metadata) if metadata else None
        }
        
        self.insert(data)
        logger.info(f"创建文档记录：{original_filename}, doc_id={doc_id}")
        
        return self.get_by_id(doc_id)
    
    # ==================== 文档查询 ====================
    
    def get_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """根据 doc_id 获取文档"""
        return self.find_one({'doc_uuid': doc_id})
    
    def get_by_kb(self, kb_id: str, status: int = None,
                  limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取知识库的文档列表
        
        Args:
            kb_id: 知识库 ID
            status: 状态筛选
            limit: 限制数量
            
        Returns:
            List[Dict]: 文档列表
        """
        conditions = {'kb_uuid': kb_id}
        if status is not None:
            conditions['status'] = status
        
        return self.find_by(
            conditions,
            order_by='created_at DESC',
            limit=limit
        )
    
    def get_user_documents(self, user_id: str, status: int = None,
                           limit: int = 100) -> List[Dict[str, Any]]:
        """获取用户的文档列表"""
        conditions = {'user_id': user_id}
        if status is not None:
            conditions['status'] = status
        
        return self.find_by(
            conditions,
            order_by='created_at DESC',
            limit=limit
        )
    
    def get_pending_documents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取待处理的文档"""
        return self.find_by(
            {'status': 0},
            order_by='created_at ASC',
            limit=limit
        )
    
    def get_failed_documents(self, kb_id: str = None,
                             limit: int = 20) -> List[Dict[str, Any]]:
        """获取处理失败的文档"""
        conditions = {'status': 3}
        if kb_id:
            conditions['kb_uuid'] = kb_id
        
        return self.find_by(
            conditions,
            order_by='created_at DESC',
            limit=limit
        )
    
    # ==================== 文档状态更新 ====================
    
    def mark_processing(self, doc_id: str) -> int:
        """标记文档为处理中"""
        return self.update({'doc_uuid': doc_id}, {'status': 1})
    
    def mark_done(self, doc_id: str, chunk_count: int, total_tokens: int) -> int:
        """标记文档处理完成"""
        return self.update(
            {'doc_uuid': doc_id},
            {
                'status': 2, 
                'chunk_count': chunk_count, 
                'total_tokens': total_tokens,
                'total_chunks': chunk_count,
                'processed_chunks': chunk_count
            }
        )
    
    def update_total_chunks(self, doc_id: str, total_chunks: int) -> int:
        """更新总切片数（解析完成后调用）"""
        return self.update(
            {'doc_uuid': doc_id},
            {'total_chunks': total_chunks}
        )
    
    def update_processed_chunks(self, doc_id: str, processed_count: int) -> int:
        """流式更新已处理切片数（每处理一个 chunk 调用）"""
        # 获取当前 total_chunks
        doc = self.get_by_id(doc_id)
        total_chunks = doc.get('total_chunks', 0) if doc else 0
        
        # 计算状态：如果已处理数等于总数，标记为完成
        status = 2 if (total_chunks > 0 and processed_count >= total_chunks) else 1
        
        return self.update(
            {'doc_uuid': doc_id},
            {
                'processed_chunks': processed_count,
                'status': status
            }
        )
    
    def update_progress_batch(self, doc_id: str, processed_count: int, total_chunks: int) -> int:
        """批量更新进度（同时更新 total 和 processed）"""
        status = 2 if processed_count >= total_chunks else 1
        
        return self.update(
            {'doc_uuid': doc_id},
            {
                'total_chunks': total_chunks,
                'processed_chunks': processed_count,
                'status': status
            }
        )
    
    def mark_failed(self, doc_id: str, error_message: str) -> int:
        """标记文档处理失败"""
        return self.update(
            {'doc_uuid': doc_id},
            {'status': 3, 'processing_error': error_message}
        )
    
    def update_processing_error(self, doc_id: str, error_message: str) -> int:
        """更新处理错误信息"""
        return self.update(
            {'doc_uuid': doc_id},
            {'processing_error': error_message}
        )
    
    # ==================== 文档更新 ====================
    
    def update_title(self, doc_id: str, title: str) -> int:
        """更新文档标题"""
        return self.update({'doc_uuid': doc_id}, {'title': title})
    
    def update_metadata(self, doc_id: str, metadata: dict) -> int:
        """更新文档元数据"""
        return self.update(
            {'doc_uuid': doc_id},
            {'metadata': json.dumps(metadata) if metadata else None}
        )
    
    def increment_version(self, doc_id: str) -> int:
        """增加版本号"""
        return self.execute(
            "UPDATE document SET version = version + 1 WHERE doc_uuid = %s",
            (doc_id,)
        )
    
    def update_stats(self, doc_id: str, chunk_count: int, 
                     total_tokens: int) -> int:
        """更新文档统计"""
        return self.update(
            {'doc_uuid': doc_id},
            {'chunk_count': chunk_count, 'total_tokens': total_tokens}
        )
    
  # ==================== 文档删除 ====================
    
    def delete_document(self, doc_id: str) -> int:
        """硬删除文档（从数据库彻底删除）"""
        return self.execute(
            "DELETE FROM document WHERE doc_uuid = %s",
            (doc_id,)
        )
    
    def delete_by_kb(self, kb_id: str) -> int:
        """硬删除知识库的所有文档"""
        return self.execute(
            "DELETE FROM document WHERE kb_uuid = %s",
            (kb_id,)
        )
    
    # ==================== 统计 ====================
    
    def get_document_count(self, kb_id: str = None, 
                           user_id: str = None,
                           status: int = None) -> int:
        """获取文档数量"""
        conditions = {}
        if kb_id:
            conditions['kb_uuid'] = kb_id
        if user_id:
            conditions['user_id'] = user_id
        if status is not None:
            conditions['status'] = status
        
        return self.count(conditions) if conditions else 0
    
    def get_kb_total_tokens(self, kb_id: str) -> int:
        """获取知识库的总 token 数"""
        sql = "SELECT COALESCE(SUM(total_tokens), 0) as total FROM document WHERE kb_uuid = %s AND status = 2"
        result = self.fetch_one(sql, (kb_id,))
        return result['total'] if result else 0
    
    def search_documents(self, kb_id: str, keyword: str,
                         limit: int = 20) -> List[Dict[str, Any]]:
        """搜索文档"""
        sql = """
            SELECT * FROM document
            WHERE kb_uuid = %s AND (title LIKE %s OR original_filename LIKE %s)
            AND status = 2
            ORDER BY created_at DESC
            LIMIT %s
        """
        params = (kb_id, f'%{keyword}%', f'%{keyword}%', limit)
        return self.fetch_all(sql, params)
