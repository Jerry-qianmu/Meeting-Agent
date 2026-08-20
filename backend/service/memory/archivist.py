# -*- coding: utf-8 -*-
"""
InterviewArchivist - 记忆组织者

轻量模式（每次 tick，无 LLM）+ 深度周期（用户空闲 ≥ 阈值时，LLM 密集）
"""

import logging
import asyncio
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from dashscope import Generation

from .config import MemoryConfig
from .prompts import ARCHIVIST_CLASSIFY_SYSTEM, ARCHIVIST_CLASSIFY_USER

logger = logging.getLogger(__name__)


class InterviewArchivist:
    """记忆组织者"""

    def __init__(self, db_client, api_key: str = None,
                 llm_model: str = None,
                 deep_llm_model: str = None):
        from database.mysql.repository.memory_fragment_repository import MemoryFragmentRepository
        from database.mysql.repository.memory_entity_repository import MemoryEntityRepository
        from database.mysql.repository.memory_episode_repository import MemoryEpisodeRepository
        from database.mysql.repository.cognitive_model_repository import CognitiveModelRepository
        from .entity_resolver import EntityResolver
        from .consolidator import Consolidator

        self.db_client = db_client
        self.api_key = api_key or MemoryConfig.DASHSCOPE_API_KEY
        self.llm_model = llm_model or MemoryConfig.MEMORY_LLM_MODEL
        self.deep_llm_model = deep_llm_model or MemoryConfig.MEMORY_DEEP_LLM_MODEL

        self.fragment_repo = MemoryFragmentRepository(db_client)
        self.entity_repo = MemoryEntityRepository(db_client)
        self.episode_repo = MemoryEpisodeRepository(db_client)
        self.cognitive_repo = CognitiveModelRepository(db_client)
        self.entity_resolver = EntityResolver(api_key, llm_model)
        self.consolidator = Consolidator(db_client, api_key, deep_llm_model)

        self._last_deep_cycle: Dict[str, datetime] = {}

    async def start_tick_loop(self, interval_seconds: int = 120):
        """启动后台 tick 循环"""
        logger.info(f"[Archivist] 启动 tick 循环，间隔 {interval_seconds}s")
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self._run_tick()
            except asyncio.CancelledError:
                logger.info("[Archivist] tick 循环已停止")
                break
            except Exception as e:
                logger.error(f"[Archivist] tick 异常: {e}", exc_info=True)

    async def _run_tick(self):
        """单次 tick"""
        from database.mysql.mysql_client import get_db_client
        db = get_db_client()
        if not db:
            return

        sql = """SELECT DISTINCT user_id FROM memory_fragment
                 WHERE deleted_at IS NULL AND lifecycle_status = 'active'
                 UNION
                 SELECT DISTINCT user_id FROM memory_entity
                 WHERE deleted_at IS NULL"""
        try:
            rows = db.query_all(sql)
        except Exception:
            return

        for row in rows:
            user_id = row['user_id']
            try:
                # 轻量模式
                self._lightweight_link(user_id)
                self._expire_cognitive_model(user_id)
                self._merge_duplicate_entities(user_id)

                # 深度周期
                if self._should_deep_cycle(user_id):
                    logger.info(f"[Archivist] 触发深度周期: user={user_id}")
                    await self._deep_cycle(user_id)
                    self._last_deep_cycle[user_id] = datetime.now()
            except Exception as e:
                logger.error(f"[Archivist] tick 处理失败: user={user_id}, {e}")

    # ==================== 轻量模式 ====================

    def _lightweight_link(self, user_id: str):
        """名称匹配将未链接碎片关联到已有实体"""
        unlinked = self.fragment_repo.get_unlinked_fragments(user_id, limit=50)
        if not unlinked:
            return

        entities = self.entity_repo.get_user_entities(user_id, limit=200)
        if not entities:
            return

        linked_count = 0
        for frag in unlinked:
            extracted = self.entity_resolver.extract_entities_regex(frag.get('content', ''))
            for ent in extracted:
                matched = self.entity_resolver.find_matching_entity(
                    ent['name'], ent['type'], entities
                )
                if matched:
                    self.fragment_repo.link_to_entity(frag['fragment_id'], matched['entity_id'])
                    self.entity_repo.update_fragment_count(matched['entity_id'], 1)
                    linked_count += 1
                    break

        if linked_count > 0:
            logger.info(f"[Archivist] 轻量链接: {linked_count} 条碎片")

    def _expire_cognitive_model(self, user_id: str):
        """过期认知模型条目"""
        self.cognitive_repo.delete_expired(user_id)

    def _merge_duplicate_entities(self, user_id: str):
        """合并重复实体"""
        duplicates = self.entity_repo.find_duplicate_entities(user_id)
        for dup in duplicates:
            entity_ids = dup.get('entity_ids', '').split(',')
            if len(entity_ids) < 2:
                continue
            keep_id = entity_ids[0]
            for remove_id in entity_ids[1:]:
                fragments = self.fragment_repo.get_user_fragments(
                    user_id, entity_id=remove_id, limit=1000
                )
                for frag in fragments:
                    self.fragment_repo.link_to_entity(frag['fragment_id'], keep_id)
                    self.entity_repo.update_fragment_count(keep_id, 1)
                    self.entity_repo.update_fragment_count(remove_id, -1)

    # ==================== 深度周期 ====================

    def _should_deep_cycle(self, user_id: str) -> bool:
        """判断是否触发深度周期"""
        last = self._last_deep_cycle.get(user_id)
        if not last:
            unlinked = self.fragment_repo.get_unlinked_fragments(user_id, limit=1)
            seeds = self.entity_repo.get_seed_entities(user_id, limit=1)
            if unlinked or seeds:
                return True
            return False
        idle_minutes = (datetime.now() - last).total_seconds() / 60
        return idle_minutes >= MemoryConfig.ARCHIVIST_DEEP_CYCLE_IDLE_MINUTES

    async def _deep_cycle(self, user_id: str):
        """深度周期"""
        await self._classify_unlinked_fragments(user_id)
        self._graduate_seed_entities(user_id)
        self.consolidator.consolidate_all_entities(user_id)
        self._regenerate_entity_overviews(user_id)

    async def _classify_unlinked_fragments(self, user_id: str):
        """LLM 分类未链接碎片"""
        unlinked = self.fragment_repo.get_unlinked_fragments(user_id, limit=20)
        if not unlinked:
            return

        entities = self.entity_repo.get_all_entity_names(user_id)
        if not entities:
            for frag in unlinked:
                extracted = self.entity_resolver.extract_entities(frag['content'])
                for ent in extracted:
                    existing = self.entity_repo.get_by_name_and_type(
                        user_id, ent['name'], ent['type']
                    )
                    if not existing:
                        new_entity = self.entity_repo.create_entity(
                            user_id=user_id, name=ent['name'],
                            entity_type=ent['type'], status='seed',
                        )
                        self.fragment_repo.link_to_entity(frag['fragment_id'], new_entity['entity_id'])
                        self.entity_repo.update_fragment_count(new_entity['entity_id'], 1)
                    else:
                        self.fragment_repo.link_to_entity(frag['fragment_id'], existing['entity_id'])
                        self.entity_repo.update_fragment_count(existing['entity_id'], 1)
            return

        entity_list = "\n".join([f"- {e['name']} ({e['entity_type']})" for e in entities])
        frag_list = "\n".join([f"- [{f['fragment_id'][:8]}] {f['content']}" for f in unlinked])

        messages = [
            {"role": "system", "content": ARCHIVIST_CLASSIFY_SYSTEM.format(existing_entities=entity_list)},
            {"role": "user", "content": ARCHIVIST_CLASSIFY_USER.format(fragments=frag_list)},
        ]

        try:
            from service.llm_client import llm_call
            from config.settings import Settings
            cfg = Settings().get_llm_config("memory", model=self.llm_model)
            llm_result = llm_call(messages=messages, model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"] or self.api_key, base_url=cfg["base_url"])
            if llm_result["status_code"] != 200:
                return

            content = llm_result["content"].strip()
            result = self._parse_json(content)
            if not result or 'classifications' not in result:
                return

            for cls in result['classifications']:
                frag_id_prefix = cls.get('fragment_id', '')
                entity_name = cls.get('entity_name', '')
                is_new = cls.get('is_new', False)

                matched_frag = None
                for f in unlinked:
                    if f['fragment_id'].startswith(frag_id_prefix):
                        matched_frag = f
                        break
                if not matched_frag or not entity_name:
                    continue

                if is_new:
                    entity_type = cls.get('entity_type', 'concept')
                    new_entity = self.entity_repo.create_entity(
                        user_id=user_id, name=entity_name,
                        entity_type=entity_type, status='seed',
                    )
                    self.fragment_repo.link_to_entity(matched_frag['fragment_id'], new_entity['entity_id'])
                    self.entity_repo.update_fragment_count(new_entity['entity_id'], 1)
                else:
                    all_ents = self.entity_repo.get_user_entities(user_id, limit=200)
                    entity = next((e for e in all_ents if e['name'] == entity_name), None)
                    if entity:
                        self.fragment_repo.link_to_entity(matched_frag['fragment_id'], entity['entity_id'])
                        self.entity_repo.update_fragment_count(entity['entity_id'], 1)
        except Exception as e:
            logger.error(f"[Archivist] 分类失败: {e}")

    def _graduate_seed_entities(self, user_id: str):
        """种子实体毕业"""
        seeds = self.entity_repo.get_seed_entities(user_id, limit=100)
        for seed in seeds:
            if seed['fragment_count'] >= MemoryConfig.ENTITY_SEED_GRADUATE_THRESHOLD:
                self.entity_repo.update_status(seed['entity_id'], 'active')
                logger.info(f"[Archivist] 实体毕业: {seed['name']} (fragments={seed['fragment_count']})")

    def _regenerate_entity_overviews(self, user_id: str):
        """重新生成实体概述"""
        entities = self.entity_repo.get_user_entities(user_id, status='active', limit=20)
        for entity in entities:
            fragments = self.fragment_repo.get_user_fragments(
                user_id, entity_id=entity['entity_id'], limit=10
            )
            if not fragments:
                continue
            recent = [f['content'] for f in fragments[:5]]
            overview = f"{entity['name']}相关记忆：\n" + "\n".join(f"- {c}" for c in recent)
            self.entity_repo.update_description(entity['entity_id'], overview)

    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return None
