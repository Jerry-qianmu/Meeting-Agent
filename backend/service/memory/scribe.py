# -*- coding: utf-8 -*-
"""
InterviewScribe - 碎片提取器

从面试对话中提取记忆碎片（Fragments）
"""

import logging
import json
import re
from typing import List, Dict, Any, Optional

from dashscope import Generation

from .models import FragmentType
from .prompts import SCRIBE_EXTRACTION_SYSTEM, SCRIBE_EXTRACTION_USER
from .config import MemoryConfig
from .entity_resolver import EntityResolver

logger = logging.getLogger(__name__)


class InterviewScribe:
    """从面试对话中提取记忆碎片"""

    def __init__(self, db_client, api_key: str,
                 llm_model: str = None,
                 embedding_service=None,
                 milvus_service=None):
        from database.mysql.repository.memory_fragment_repository import MemoryFragmentRepository
        from database.mysql.repository.message_repository import MessageRepository

        self.fragment_repo = MemoryFragmentRepository(db_client)
        self.message_repo = MessageRepository(db_client)
        self.api_key = api_key or MemoryConfig.DASHSCOPE_API_KEY
        self.llm_model = llm_model or MemoryConfig.MEMORY_LLM_MODEL
        self.entity_resolver = EntityResolver(self.api_key, self.llm_model)
        self.embedding_service = embedding_service
        self.milvus_service = milvus_service

    def should_extract(self, session_id: str, message_count: int,
                       last_activity_minutes: float) -> bool:
        """判断是否应该触发提取"""
        if message_count >= MemoryConfig.SCRIBE_BACKLOG_THRESHOLD:
            return True
        if last_activity_minutes >= MemoryConfig.SCRIBE_TRIGGER_SILENCE_MINUTES:
            return True
        return False

    def extract_from_session(self, session_id: str, user_id: str) -> List[Dict[str, Any]]:
        """从完整会话中提取碎片"""
        messages = self.message_repo.get_session_messages(session_id, limit=200)
        if not messages:
            logger.info(f"[Scribe] 会话 {session_id} 无消息，跳过提取")
            return []
        return self._extract_and_store(messages, session_id, user_id)

    def extract_incremental(self, session_id: str, user_id: str,
                            new_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """增量提取（仅处理新消息）"""
        if not new_messages:
            return []
        return self._extract_and_store(new_messages, session_id, user_id)

    def _extract_and_store(self, messages: List[Dict[str, Any]],
                           session_id: str, user_id: str) -> List[Dict[str, Any]]:
        """提取碎片并存储"""
        formatted = self._format_messages(messages)
        if not formatted:
            return []

        extracted = self._call_llm_extract(formatted)
        if not extracted:
            logger.info(f"[Scribe] 未提取到碎片: session={session_id}")
            return []

        fragments = []
        for fact in extracted:
            fragment_type = fact.get('type', 'fact')
            if fragment_type not in [e.value for e in FragmentType]:
                fragment_type = 'fact'

            fragment = self.fragment_repo.create_fragment(
                user_id=user_id,
                content=fact['content'],
                fragment_type=fragment_type,
                session_uuid=session_id,
                importance_score=fact.get('importance', 0.5),
            )
            fragments.append(fragment)

            entity_names = fact.get('entities', [])
            if entity_names:
                self._link_entities_async(fragment['fragment_id'], user_id, entity_names)

        logger.info(f"[Scribe] 提取 {len(fragments)} 条碎片: session={session_id}")

        # Milvus 向量索引
        if fragments:
            self._index_to_milvus(user_id, fragments)

        return fragments

    def _format_messages(self, messages: List[Dict[str, Any]]) -> str:
        """将消息格式化为 LLM 输入"""
        lines = []
        for msg in messages:
            role = msg.get('role', 0)
            content = msg.get('content', '') or ''
            if not content:
                continue
            if len(content) > 500:
                content = content[:500] + '...'
            role_name = '用户' if role == 0 else '助手' if role == 1 else '系统'
            lines.append(f"{role_name}：{content}")
        return '\n'.join(lines)

    def _call_llm_extract(self, formatted_messages: str) -> List[Dict[str, Any]]:
        """调用 LLM 提取碎片"""
        messages = [
            {"role": "system", "content": SCRIBE_EXTRACTION_SYSTEM},
            {"role": "user", "content": SCRIBE_EXTRACTION_USER.format(messages=formatted_messages)},
        ]
        try:
            from service.llm_client import llm_call
            from config.settings import Settings
            cfg = Settings().get_llm_config("memory", model=self.llm_model)
            result = llm_call(messages=messages, model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"] or self.api_key, base_url=cfg["base_url"])
            if result["status_code"] == 200:
                content = result["content"].strip()
                logger.info(f"[Scribe] LLM 返回: {content[:300]}")
                return self._parse_extraction_result(content)
            else:
                logger.warning(f"[Scribe] LLM API 错误: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"[Scribe] LLM 提取失败: {e}", exc_info=True)
            return []

    def _parse_extraction_result(self, content: str) -> List[Dict[str, Any]]:
        """解析 LLM 提取结果"""
        try:
            data = json.loads(content)
            if isinstance(data, list):
                valid = []
                for item in data:
                    if isinstance(item, dict) and 'content' in item:
                        if len(item['content']) > MemoryConfig.SCRIBE_MAX_FRAGMENT_LENGTH:
                            item['content'] = item['content'][:MemoryConfig.SCRIBE_MAX_FRAGMENT_LENGTH]
                        valid.append(item)
                return valid
            return []
        except json.JSONDecodeError:
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return data if isinstance(data, list) else []
                except json.JSONDecodeError:
                    pass
            return []

    def _link_entities_async(self, fragment_id: str, user_id: str,
                             entity_names: List[str]):
        """链接实体（简化版：查找或创建种子实体）"""
        try:
            from database.mysql.mysql_client import get_db_client
            from database.mysql.repository.memory_entity_repository import MemoryEntityRepository
            from database.mysql.repository.memory_fragment_repository import MemoryFragmentRepository

            db_client = get_db_client()
            if not db_client:
                return

            entity_repo = MemoryEntityRepository(db_client)
            fragment_repo = MemoryFragmentRepository(db_client)

            for name in entity_names:
                if not name or len(name) > 200:
                    continue

                # 查找已有实体
                all_entities = entity_repo.get_user_entities(user_id, limit=200)
                matched = None
                for etype in ['company', 'position', 'technology', 'concept', 'event']:
                    matched = self.entity_resolver.find_matching_entity(name, etype, all_entities)
                    if matched:
                        break

                if matched:
                    fragment_repo.link_to_entity(fragment_id, matched['entity_id'])
                    entity_repo.update_fragment_count(matched['entity_id'], 1)
                else:
                    entity_type = self._guess_entity_type(name)
                    new_entity = entity_repo.create_entity(
                        user_id=user_id, name=name,
                        entity_type=entity_type, status='seed',
                    )
                    fragment_repo.link_to_entity(fragment_id, new_entity['entity_id'])
                    entity_repo.update_fragment_count(new_entity['entity_id'], 1)
        except Exception as e:
            logger.error(f"[Scribe] 实体链接失败: {e}")

    def _guess_entity_type(self, name: str) -> str:
        """根据名称猜测实体类型"""
        name_lower = name.lower()
        tech_kw = ['python', 'java', 'redis', 'mysql', 'docker', 'tcp', 'http',
                    '树', '表', '队列', '栈', '堆', '图']
        if any(kw in name_lower for kw in tech_kw):
            return 'technology'
        company_kw = ['字节', '腾讯', '阿里', '百度', '美团', '京东', '华为']
        if any(kw in name for kw in company_kw):
            return 'company'
        event_kw = ['一面', '二面', '三面', '笔试', '面试', '校招', '社招']
        if any(kw in name for kw in event_kw):
            return 'event'
        return 'concept'

    def _index_to_milvus(self, user_id: str, fragments: List[Dict[str, Any]]):
        """将碎片索引到 Milvus"""
        try:
            if not self.embedding_service or not self.milvus_service:
                return
            from .memory_milvus_service import MemoryMilvusService
            milvus = MemoryMilvusService(self.milvus_service.client, self.embedding_service)
            milvus.index_fragments(user_id, fragments)
        except Exception as e:
            logger.warning(f"[Scribe] Milvus 索引失败: {e}")
