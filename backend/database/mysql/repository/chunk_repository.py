# -*- coding: utf-8 -*-
"""
Chunk 数据访问层
"""

from typing import Optional, Dict, Any, List
import logging
import uuid
import json

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ChunkRepository(BaseRepository):
    """文档切片表 Repository"""
    
    def __init__(self, db_client):
        super().__init__(db_client)
        self.table_name = 'chunk'
    
    def create_chunk(self, doc_id: str, kb_id: str,
                     content: str, chunk_order: int,
                     token_count: int,
                     start_char: int = None, end_char: int = None,
                     page_number: int = None,
                     section_title: str = None,
                     description: str = None,
                     keywords: list = None,
                     heading_path: list = None,
                     metadata: dict = None,
                     chunk_id: str = None) -> str:
        """
        创建文档切片

        Args:
            doc_id: 文档 ID
            kb_id: 知识库 ID
            content: 切片内容
            chunk_order: 切片顺序
            token_count: token 数量
            start_char: 起始字符位置
            end_char: 结束字符位置
            page_number: PDF 页码
            section_title: 章节标题
            description: chunk 摘要描述（LLM 生成）
            keywords: 关键词列表
            heading_path: 标题路径
            metadata: 扩展元数据
            chunk_id: 外部传入的 chunk UUID（可选，不传则自动生成）

        Returns:
            str: chunk_uuid
        """
        if not chunk_id:
            chunk_id = str(uuid.uuid4())
        data = {
            'chunk_uuid': chunk_id,
            'doc_uuid': doc_id,
            'kb_uuid': kb_id,
            'content': content,
            'chunk_order': chunk_order,
            'start_char': start_char,
            'end_char': end_char,
            'page_number': page_number,
            'section_title': section_title,
            'token_count': token_count,
            'description': description,
            'keywords': json.dumps(keywords, ensure_ascii=False) if keywords else None,
            'heading_path': json.dumps(heading_path, ensure_ascii=False) if heading_path else None,
            'metadata': json.dumps(metadata, ensure_ascii=False) if metadata else None
        }

        self.insert(data)
        logger.debug(f"创建切片：chunk_uuid={chunk_id}, order={chunk_order}")

        return chunk_id
    
    def create_chunks_batch(self, chunks_data: List[Dict[str, Any]]) -> int:
        """
        批量创建切片
        
        Args:
            chunks_data: 切片数据列表
            
        Returns:
            int: 创建的数量
        """
        # 为每个切片生成 UUID
        for chunk in chunks_data:
            chunk['chunk_uuid'] = str(uuid.uuid4())
        
        return self.insert_batch(chunks_data)
    
    def get_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """根据 chunk_id 获取切片"""
        return self.find_one({'chunk_uuid': chunk_id})
    
    def get_by_doc(self, doc_id: str) -> List[Dict[str, Any]]:
        """获取文档的所有切片（按顺序）"""
        return self.find_by(
            {'doc_uuid': doc_id},
            order_by='chunk_order ASC'
        )
    
    def get_by_kb(self, kb_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取知识库的所有切片"""
        return self.find_by(
            {'kb_uuid': kb_id},
            order_by='created_at DESC',
            limit=limit
        )
    
    def get_by_section(self, kb_id: str, section_title: str) -> List[Dict[str, Any]]:
        """获取特定章节的切片"""
        return self.find_by(
            {'kb_uuid': kb_id, 'section_title': section_title},
            order_by='chunk_order ASC'
        )
    
    def get_chunks_with_page(self, doc_id: str, page_number: int) -> List[Dict[str, Any]]:
        """获取特定页码的切片"""
        return self.find_by(
            {'doc_uuid': doc_id, 'page_number': page_number},
            order_by='chunk_order ASC'
        )
    
    def delete_chunk(self, chunk_id: str) -> int:
        """硬删除切片"""
        return self.execute(
            "DELETE FROM chunk WHERE chunk_uuid = %s",
            (chunk_id,)
        )
    
    def delete_by_doc(self, doc_id: str) -> int:
        """硬删除文档的所有切片"""
        return self.execute(
            "DELETE FROM chunk WHERE doc_uuid = %s",
            (doc_id,)
        )
    
    def delete_by_kb(self, kb_id: str) -> int:
        """硬删除知识库的所有切片"""
        return self.execute(
            "DELETE FROM chunk WHERE kb_uuid = %s",
            (kb_id,)
        )
    
    def count_by_doc(self, doc_id: str) -> int:
        """统计文档的切片数量"""
        return self.count({'doc_uuid': doc_id})
    
    def count_by_kb(self, kb_id: str) -> int:
        """统计知识库的切片数量"""
        return self.count({'kb_uuid': kb_id})
    
    def get_total_tokens_by_doc(self, doc_id: str) -> int:
        """获取文档的总 token 数"""
        sql = "SELECT COALESCE(SUM(token_count), 0) as total FROM chunk WHERE doc_uuid = %s"
        result = self.fetch_one(sql, (doc_id,))
        return result['total'] if result else 0
    
    def get_total_tokens_by_kb(self, kb_id: str) -> int:
        """获取知识库的总 token 数"""
        sql = "SELECT COALESCE(SUM(token_count), 0) as total FROM chunk WHERE kb_uuid = %s"
        result = self.fetch_one(sql, (kb_id,))
        return result['total'] if result else 0
