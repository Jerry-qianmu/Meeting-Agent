# -*- coding: utf-8 -*-
"""
短期记忆服务
负责短期记忆的提取、存储、检索和衰减计算
"""

import logging
import os
import sys
from typing import Optional, Dict, Any, List
from datetime import datetime

# 添加路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.insert(0, grand_parent_dir)

from database.mysql.repository.short_term_memory_repository import ShortTermMemoryRepository
from database.mysql.repository.message_repository import MessageRepository
from database.mysql.repository.session_repository import SessionRepository

logger = logging.getLogger(__name__)


class ShortTermMemoryService:
    """短期记忆服务"""
    
    def __init__(self, db_client):
        """
        初始化短期记忆服务
        
        Args:
            db_client: MySQL 数据库客户端
        """
        self.memory_repo = ShortTermMemoryRepository(db_client)
        self.message_repo = MessageRepository(db_client)
        self.session_repo = SessionRepository(db_client)
        
        # 配置参数
        self.max_memories_per_session = 100  # 每个会话最大记忆数
        self.min_relevance_threshold = 0.3   # 最小相关性阈值
    
    def extract_memory_from_conversation(self, session_id: str, user_id: str,
                                         user_query: str, assistant_answer: str,
                                         message_id: str = None,
                                         entities: Dict = None,
                                         key_facts: List[Dict] = None) -> Dict[str, Any]:
        """
        从对话中提取并创建短期记忆
        
        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            user_query: 用户问题
            assistant_answer: 助手回答
            message_id: 关联的消息 ID
            entities: 提取的实体
            key_facts: 关键事实
            
        Returns:
            Dict: 创建的记忆数据
        """
        # 生成摘要（简单版本：截断）
        query_summary = self._generate_query_summary(user_query)
        answer_summary = self._generate_answer_summary(assistant_answer)
        
        # 计算基础相关性分数
        base_score = self._calculate_base_relevance(user_query, assistant_answer)
        
        # 创建记忆
        memory = self.memory_repo.create_memory(
            session_id=session_id,
            user_id=user_id,
            query_summary=query_summary,
            answer_summary=answer_summary,
            entities=entities,
            key_facts=key_facts,
            message_id=message_id,
            base_relevance_score=base_score
        )
        
        logger.info(f"短期记忆创建成功：session={session_id}, score={base_score:.2f}")
        
        return memory
    
    def get_context_for_query(self, session_id: str, user_id: str,
                             query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        为当前查询获取相关的短期记忆上下文
        
        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            query: 当前查询
            top_k: 返回数量
            
        Returns:
            List[Dict]: 相关记忆列表（按相关性排序）
        """
        # 获取会话的所有记忆
        memories = self.memory_repo.get_session_memories(
            session_id=session_id,
            limit=self.max_memories_per_session,
            order_by='created_at DESC'
        )
        
        if not memories:
            return []
        
        # 计算每个记忆的当前相关性分数（包含时间衰减）
        memories_with_scores = self.memory_repo.get_decay_scores(memories)
        
        # 计算与当前查询的相似度分数
        for memory in memories_with_scores:
            memory['query_similarity'] = self._calculate_query_similarity(
                query, 
                memory.get('query_summary', ''),
                memory.get('answer_summary', '')
            )
        
        # 综合评分：time_decay_score * query_similarity
        for memory in memories_with_scores:
            current_score = memory.get('current_relevance_score', 0)
            similarity = memory.get('query_similarity', 0)
            memory['final_score'] = current_score * similarity
        
        # 过滤低于阈值的记忆
        filtered_memories = [
            m for m in memories_with_scores 
            if m['final_score'] >= self.min_relevance_threshold
        ]
        
        # 按最终分数排序，取 top_k
        filtered_memories.sort(key=lambda x: x['final_score'], reverse=True)
        top_memories = filtered_memories[:top_k]
        
        # 更新访问次数
        for memory in top_memories:
            self.memory_repo.increment_access_count(memory['memory_id'])
        
        logger.info(f"短期记忆检索：query='{query[:20]}...', found={len(top_memories)}")
        
        return top_memories
    
    def get_session_context(self, session_id: str, user_id: str,
                           max_memories: int = 10) -> List[Dict[str, Any]]:
        """
        获取会话的短期记忆上下文（最近 + 相关）
        
        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            max_memories: 最大返回数量
            
        Returns:
            List[Dict]: 记忆上下文列表
        """
        # 获取最近的记忆
        recent_memories = self.memory_repo.get_recent_memories(
            session_id=session_id,
            limit=max_memories
        )
        
        # 计算衰减分数
        memories_with_scores = self.memory_repo.get_decay_scores(recent_memories)
        
        # 格式化输出
        context_list = []
        for memory in memories_with_scores:
            context_list.append({
                'memory_id': memory['memory_id'],
                'query': memory.get('query_summary', ''),
                'answer': memory.get('answer_summary', ''),
                'created_at': memory.get('created_at'),
                'relevance_score': memory.get('current_relevance_score', 0),
                'access_count': memory.get('access_count', 0)
            })
        
        return context_list
    
    def build_prompt_context(self, session_id: str, user_id: str,
                            current_query: str, max_context_tokens: int = 2000) -> str:
        """
        构建包含短期记忆的 Prompt 上下文
        
        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            current_query: 当前查询
            max_context_tokens: 最大 context token 数
            
        Returns:
            str: 格式化后的上下文
        """
        # 获取相关记忆
        relevant_memories = self.get_context_for_query(
            session_id=session_id,
            user_id=user_id,
            query=current_query,
            top_k=10
        )
        
        if not relevant_memories:
            return ""
        
        # 构建上下文
        context_parts = ["\n=== 历史对话记忆 ==="]
        total_tokens = 0
        
        for i, memory in enumerate(relevant_memories, 1):
            query = memory.get('query', '')
            answer = memory.get('answer', '')
            
            # 估算 token 数
            estimated_tokens = len(query) + len(answer)
            
            if total_tokens + estimated_tokens > max_context_tokens:
                break
            
            context_parts.append(f"\n[{i}] 用户：{query}")
            context_parts.append(f"    助手：{answer}")
            total_tokens += estimated_tokens
        
        context_parts.append("===\n")
        
        return "\n".join(context_parts)
    
    def update_memory_after_interaction(self, memory_id: str, 
                                       relevance_feedback: float = None):
        """
        交互后更新记忆的相关性分数
        
        Args:
            memory_id: 记忆 ID
            relevance_feedback: 用户反馈的相关性分数（可选）
        """
        if relevance_feedback is not None:
            # 使用用户反馈更新
            self.memory_repo.update_relevance_score(memory_id, relevance_feedback)
            logger.info(f"记忆相关性更新：memory={memory_id}, score={relevance_feedback}")
        
        # 增加访问次数
        self.memory_repo.increment_access_count(memory_id)
    
    def _generate_query_summary(self, query: str, max_length: int = 100) -> str:
        """生成问题摘要"""
        if not query:
            return ""
        
        # 简单截断
        summary = query.strip()
        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."
        
        return summary
    
    def _generate_answer_summary(self, answer: str, max_length: int = 300) -> str:
        """生成答案摘要"""
        if not answer:
            return ""
        
        # 简单截断
        summary = answer.strip()
        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."
        
        return summary
    
    def _calculate_base_relevance(self, query: str, answer: str) -> float:
        """
        计算基础相关性分数
        
        基于回答长度和内容质量估算
        """
        if not answer:
            return 0.3
        
        # 长度评分（回答太短可能质量不高）
        answer_len = len(answer)
        if answer_len < 50:
            length_score = 0.4
        elif answer_len < 200:
            length_score = 0.7
        else:
            length_score = 1.0
        
        # 内容质量评分（简单的关键词检测）
        quality_keywords = ['根据', '以下是', '总结', '因此', '所以', '总之']
        has_quality_markers = any(kw in answer for kw in quality_keywords)
        quality_score = 0.8 if has_quality_markers else 0.6
        
        # 综合分数
        base_score = (length_score * 0.6 + quality_score * 0.4)
        
        return round(base_score, 2)
    
    def _calculate_query_similarity(self, current_query: str, 
                                   memory_query: str, memory_answer: str) -> float:
        """
        计算当前查询与历史记忆的相似度
        
        简单实现：基于关键词重叠
        TODO: 使用 embedding 进行语义相似度计算
        """
        if not current_query or not (memory_query or memory_answer):
            return 0.0
        
        # 提取关键词（简单分词）
        current_keywords = set(self._extract_keywords(current_query))
        memory_keywords = set(self._extract_keywords(memory_query + " " + memory_answer))
        
        if not current_keywords or not memory_keywords:
            return 0.0
        
        # Jaccard 相似度
        intersection = current_keywords & memory_keywords
        union = current_keywords | memory_keywords
        
        similarity = len(intersection) / len(union) if union else 0.0
        
        return round(similarity, 2)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词（简单实现）"""
        # 移除标点符号
        import re
        text = re.sub(r'[^\w\s]', '', text)
        
        # 分词（按空格和中文分词）
        words = text.split()
        
        # 过滤停用词
        stopwords = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人', 
                    '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去',
                    '你', '会', '着', '没有', '看', '好', '自己', '这'}
        
        keywords = [w for w in words if w and w not in stopwords and len(w) > 1]
        
        return keywords[:20]  # 限制关键词数量
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """获取会话的短期记忆统计信息"""
        return self.memory_repo.get_session_stats(session_id)
