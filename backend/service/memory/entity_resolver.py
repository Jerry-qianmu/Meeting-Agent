# -*- coding: utf-8 -*-
"""
实体识别与消歧服务
"""

import logging
import re
import json
from typing import List, Dict, Any, Optional

from dashscope import Generation

from .models import EntityType
from .prompts import ENTITY_RESOLVER_SYSTEM, ENTITY_RESOLVER_USER

logger = logging.getLogger(__name__)

TECH_PATTERNS = [
    r'\b(Python|Java|Go|Golang|C\+\+|JavaScript|TypeScript|Rust|Scala|Kotlin|Swift|Ruby|PHP|C#)\b',
    r'\b(Redis|MySQL|PostgreSQL|MongoDB|Elasticsearch|Kafka|RabbitMQ|RocketMQ|ClickHouse|TiDB|Neo4j)\b',
    r'\b(Docker|Kubernetes|K8s|Nginx|Git|Linux|Jenkins)\b',
    r'\b(Spring|Django|Flask|FastAPI|Express|React|Vue|Angular)\b',
    r'\b(TCP|UDP|HTTP|HTTPS|gRPC|WebSocket|REST|GraphQL)\b',
    r'\b(B\+?树|红黑树|二叉树|哈希表|链表|数组|栈|队列|堆|图|跳表)\b',
    r'\b(分布式|微服务|缓存|消息队列|负载均衡|熔断|限流|降级|CAP|BASE)\b',
]

COMPANY_PATTERNS = [
    r'(字节跳动|字节|抖音|TikTok|今日头条)',
    r'(腾讯|微信|WeChat|QQ)',
    r'(阿里巴巴|阿里|淘宝|天猫|蚂蚁金服|支付宝)',
    r'(百度|Baidu)', r'(美团|大众点评)', r'(京东|JD)',
    r'(华为|Huawei)', r'(小米|Xiaomi)', r'(网易|NetEase)',
    r'(拼多多|PDD)', r'(快手|Kuaishou)', r'(小红书|RED)',
    r'(微软|Microsoft|MS)', r'(谷歌|Google)', r'(亚马逊|Amazon|AWS)',
]

EVENT_PATTERNS = [
    r'(一面|二面|三面|四面|HR面|终面|技术面|主管面)',
    r'(笔试|机试|在线测评|OA)',
    r'(内推|校招|社招|实习)',
]


class EntityResolver:
    """面试实体识别与消歧"""

    def __init__(self, api_key: str, model: str = None):
        from .config import MemoryConfig
        self.api_key = api_key or MemoryConfig.DASHSCOPE_API_KEY
        self.model = model or MemoryConfig.MEMORY_LLM_MODEL

    def extract_entities_regex(self, text: str) -> List[Dict[str, Any]]:
        """正则预提取"""
        entities = []
        seen = set()

        for pattern in TECH_PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                name = m.group(1).strip()
                if name.lower() not in seen:
                    seen.add(name.lower())
                    entities.append({'name': name, 'type': EntityType.TECHNOLOGY.value,
                                    'description': None, 'confidence': 0.9})

        for pattern in COMPANY_PATTERNS:
            for m in re.finditer(pattern, text):
                name = m.group(1).strip()
                if name not in seen:
                    seen.add(name)
                    entities.append({'name': name, 'type': EntityType.COMPANY.value,
                                    'description': None, 'confidence': 0.95})

        for pattern in EVENT_PATTERNS:
            for m in re.finditer(pattern, text):
                name = m.group(1).strip()
                if name not in seen:
                    seen.add(name)
                    entities.append({'name': name, 'type': EntityType.EVENT.value,
                                    'description': None, 'confidence': 0.85})

        return entities

    def extract_entities_llm(self, text: str) -> List[Dict[str, Any]]:
        """LLM 精提取"""
        messages = [
            {"role": "system", "content": ENTITY_RESOLVER_SYSTEM},
            {"role": "user", "content": ENTITY_RESOLVER_USER.format(text=text)},
        ]
        try:
            from service.llm_client import llm_call
            from config.settings import Settings
            cfg = Settings().get_llm_config("memory", model=self.model)
            result = llm_call(messages=messages, model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"] or self.api_key, base_url=cfg["base_url"])
            if result["status_code"] == 200:
                content = result["content"].strip()
                return self._parse_llm_response(content)
            else:
                logger.warning(f"[EntityResolver] LLM API 错误: {result['status_code']}")
                return []
        except Exception as e:
            logger.error(f"[EntityResolver] LLM 提取失败: {e}")
            return []

    def extract_entities(self, text: str, use_llm: bool = True) -> List[Dict[str, Any]]:
        """两阶段实体提取：正则预提取 + LLM 精提取"""
        regex_entities = self.extract_entities_regex(text)
        seen = {e['name'].lower() for e in regex_entities}

        if use_llm and len(text) > 50:
            llm_entities = self.extract_entities_llm(text)
            for entity in llm_entities:
                if entity['name'].lower() not in seen:
                    seen.add(entity['name'].lower())
                    regex_entities.append(entity)

        return regex_entities

    def find_matching_entity(self, entity_name: str, entity_type: str,
                             existing_entities: List[Dict[str, Any]],
                             threshold: float = 0.8) -> Optional[Dict[str, Any]]:
        """在已有实体中查找匹配项（消歧）"""
        name_lower = entity_name.lower()
        for existing in existing_entities:
            existing_name = existing.get('name', '').lower()
            existing_type = existing.get('entity_type', '')
            if existing_type != entity_type:
                continue
            if name_lower == existing_name:
                return existing
            if name_lower in existing_name or existing_name in name_lower:
                return existing
            if self._string_similarity(name_lower, existing_name) >= threshold:
                return existing
        return None

    def _string_similarity(self, s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0
        shorter, longer = (s1, s2) if len(s1) <= len(s2) else (s2, s1)
        if shorter in longer:
            return len(shorter) / len(longer)
        max_len = 0
        for i in range(len(s1)):
            for j in range(len(s2)):
                k = 0
                while i + k < len(s1) and j + k < len(s2) and s1[i + k] == s2[j + k]:
                    k += 1
                max_len = max(max_len, k)
        return (2.0 * max_len) / (len(s1) + len(s2))

    def _parse_llm_response(self, content: str) -> List[Dict[str, Any]]:
        try:
            data = json.loads(content)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return data if isinstance(data, list) else []
                except json.JSONDecodeError:
                    pass
            return []
