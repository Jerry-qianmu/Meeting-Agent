"""
实体提取器 - 使用NER模型提取实体
"""

import re
from typing import List, Dict, Tuple
from transformers import pipeline
from ..config import NERConfig


class Entity:
    """实体类"""

    def __init__(self, text: str, entity_type: str, start: int, end: int, score: float = 1.0):
        self.text = text
        self.entity_type = entity_type
        self.start = start
        self.end = end
        self.score = score
        self.is_structured = False
        self.pattern_type = None
        self.context = None

    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "type": self.entity_type,
            "start": self.start,
            "end": self.end,
            "score": self.score,
            "is_structured": self.is_structured,
            "pattern_type": self.pattern_type,
            "context": self.context
        }

    def __repr__(self):
        return f"Entity(text='{self.text}', type='{self.entity_type}', structured={self.is_structured})"


class EntityExtractor:
    """实体提取器"""

    def __init__(self, config: NERConfig = None):
        self.config = config or NERConfig()
        self.ner = None
        self._load_model()

    def _load_model(self):
        """加载NER模型"""
        try:
            self.ner = pipeline(
                "ner",
                model=self.config.model_name,
                tokenizer=self.config.model_name,
                device=self.config.device
            )
            print(f"NER模型加载成功: {self.config.model_name}")
        except Exception as e:
            print(f"NER模型加载失败: {e}")
            self.ner = None

    def extract(self, text: str) -> List[Entity]:
        """提取实体"""
        if not text.strip() or self.ner is None:
            return []

        try:
            results = self.ner(text)
            entities = self._merge_subwords(text, results)
            return entities
        except Exception as e:
            print(f"实体提取失败: {e}")
            return []

    def _merge_subwords(self, text: str, ner_results: List[Dict]) -> List[Entity]:
        """合并子词为完整实体"""
        entities = []
        current_entity = None

        for item in ner_results:
            if item["entity"].startswith("B-"):
                if current_entity:
                    entities.append(current_entity)

                entity_type = item["entity"][2:]
                current_entity = Entity(
                    text=item["word"],
                    entity_type=entity_type,
                    start=item["start"],
                    end=item["end"],
                    score=float(item["score"])
                )
            elif item["entity"].startswith("I-") and current_entity:
                entity_type = item["entity"][2:]
                if entity_type == current_entity.entity_type:
                    current_entity.text += item["word"].replace("#", "")
                    current_entity.end = item["end"]
                    current_entity.score = float(min(current_entity.score, item["score"]))
            else:
                if current_entity:
                    entities.append(current_entity)
                    current_entity = None

        if current_entity:
            entities.append(current_entity)

        return entities

    def extract_structured_entities(self, text: str) -> Tuple[List[Entity], List[Entity]]:
        """提取并分类实体（结构化 vs 叙述性）"""
        entities = self.extract(text)

        structured = []
        narrative = []

        for entity in entities:
            context_result = self._analyze_context(text, entity)

            if context_result["is_structured"]:
                entity.is_structured = True
                entity.pattern_type = context_result["pattern_type"]
                entity.context = context_result["context"]
                structured.append(entity)
            else:
                narrative.append(entity)

        return structured, narrative

    def _analyze_context(self, text: str, entity: Entity, window_size: int = 30) -> Dict:
        """分析实体上下文，判断是否为结构化信息"""
        start = max(0, entity.start - window_size)
        end = min(len(text), entity.end + window_size)

        context_before = text[start:entity.start].lower()
        context_after = text[entity.end:end].lower()

        for pattern_name, keywords_dict in self.config.structured_keywords.items():
            zh_keywords = keywords_dict.get("zh", [])
            en_keywords = keywords_dict.get("en", [])
            all_keywords = zh_keywords + en_keywords

            has_keyword = any(kw in context_before for kw in all_keywords)

            if has_keyword:
                return {
                    "is_structured": True,
                    "pattern_type": pattern_name,
                    "context": context_before + entity.text + context_after
                }

        return {
            "is_structured": False,
            "pattern_type": None,
            "context": context_before + entity.text + context_after
        }

    def extract_with_regex(self, text: str) -> List[Entity]:
        """使用正则表达式补充提取实体"""
        entities = []

        phone_pattern = re.compile(r'1[3-9]\d{9}')
        for match in phone_pattern.finditer(text):
            entities.append(Entity(
                text=match.group(),
                entity_type="PHONE",
                start=match.start(),
                end=match.end()
            ))

        email_pattern = re.compile(r'\S+@\S+\.\S+')
        for match in email_pattern.finditer(text):
            entities.append(Entity(
                text=match.group(),
                entity_type="EMAIL",
                start=match.start(),
                end=match.end()
            ))

        date_pattern_cn = re.compile(r'\d{4}年\d{1,2}月\d{1,2}日')
        for match in date_pattern_cn.finditer(text):
            entities.append(Entity(
                text=match.group(),
                entity_type="TIME",
                start=match.start(),
                end=match.end()
            ))

        date_pattern_en = re.compile(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}')
        for match in date_pattern_en.finditer(text):
            entities.append(Entity(
                text=match.group(),
                entity_type="TIME",
                start=match.start(),
                end=match.end()
            ))

        return entities

    def deduplicate(self, entities: List[Entity]) -> List[Entity]:
        """去重重叠的实体"""
        if not entities:
            return []

        sorted_entities = sorted(entities, key=lambda x: (x.start, -x.end))

        deduplicated = [sorted_entities[0]]

        for entity in sorted_entities[1:]:
            last = deduplicated[-1]

            if entity.start < last.end:
                if len(entity.text) > len(last.text):
                    deduplicated[-1] = entity
            else:
                deduplicated.append(entity)

        return deduplicated
