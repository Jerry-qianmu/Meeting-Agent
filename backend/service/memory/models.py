# -*- coding: utf-8 -*-
"""
Memory Constellations 数据模型定义

所有记忆系统的数据结构，使用 Pydantic 进行验证
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# =========================
# 枚举类型
# =========================

class EntityType(str, Enum):
    """面试场景实体类型"""
    COMPANY = "company"
    POSITION = "position"
    TECHNOLOGY = "technology"
    INTERVIEWER = "interviewer"
    QUESTION = "question"
    CONCEPT = "concept"
    PROJECT = "project"
    EVENT = "event"


class FragmentType(str, Enum):
    """碎片类型"""
    FACT = "fact"
    PREFERENCE = "preference"
    FEEDBACK = "feedback"
    EXPERIENCE = "experience"


class LifecycleStatus(str, Enum):
    """生命周期状态"""
    ACTIVE = "active"
    COOLING = "cooling"
    FROZEN = "frozen"
    TOMBSTONE = "tombstone"


class EntityStatus(str, Enum):
    """实体状态"""
    SEED = "seed"
    ACTIVE = "active"
    MATURE = "mature"
    ARCHIVED = "archived"


class EpisodeType(str, Enum):
    """剧集类型"""
    INTERVIEW = "interview"
    PRACTICE = "practice"
    FEEDBACK = "feedback"
    LEARNING = "learning"


class SagaType(str, Enum):
    """传奇类型"""
    CAREER = "career"
    TECHNICAL = "technical"
    GROWTH = "growth"
    CHALLENGE = "challenge"


class CorrectionType(str, Enum):
    """修正类型"""
    FIX_FRAGMENT = "fix_fragment"
    NEW_CORRECTION = "new_correction"


# =========================
# 核心数据模型
# =========================

class MemoryFragment(BaseModel):
    """记忆碎片 - Scribe 提取的单条事实"""
    fragment_id: str
    user_id: str
    session_uuid: Optional[str] = None
    message_uuid: Optional[str] = None
    content: str = Field(..., max_length=500)
    fragment_type: FragmentType = FragmentType.FACT
    entity_id: Optional[str] = None
    consolidated: bool = False
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    lifecycle_status: LifecycleStatus = LifecycleStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MemoryEntity(BaseModel):
    """记忆实体 - 面试中的命名实体"""
    entity_id: str
    user_id: str
    name: str = Field(..., max_length=200)
    entity_type: EntityType
    description: Optional[str] = None
    fragment_count: int = 0
    episode_count: int = 0
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    status: EntityStatus = EntityStatus.SEED
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MemoryEpisode(BaseModel):
    """记忆剧集 - 整合后的叙事段落"""
    episode_id: str
    user_id: str
    entity_id: Optional[str] = None
    title: str = Field(..., max_length=300)
    content: str
    episode_type: EpisodeType = EpisodeType.INTERVIEW
    fragment_ids: Optional[List[str]] = None
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    lifecycle_status: LifecycleStatus = LifecycleStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MemorySaga(BaseModel):
    """记忆传奇 - 跨实体的长期叙事弧线"""
    saga_id: str
    user_id: str
    title: str = Field(..., max_length=300)
    summary: str
    saga_type: SagaType = SagaType.CAREER
    entity_ids: Optional[List[str]] = None
    episode_ids: Optional[List[str]] = None
    emotion_axes: Optional[Dict[str, float]] = None
    importance_score: float = Field(default=0.7, ge=0.0, le=1.0)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CognitiveModelEntry(BaseModel):
    """认知模型条目 - AI 对候选人的理解"""
    model_id: str
    user_id: str
    dimension: str
    dimension_key: str
    current_value: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_count: int = 1
    ttl_days: int = 90
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MemoryCorrection(BaseModel):
    """记忆修正 - 用户纠正记录"""
    correction_id: str
    user_id: str
    original_fragment_id: Optional[str] = None
    original_content: Optional[str] = None
    corrected_content: str = Field(..., max_length=500)
    correction_type: CorrectionType
    reason: Optional[str] = None
    created_at: Optional[datetime] = None


# =========================
# 提取结果模型（LLM 输出）
# =========================

class ExtractedFact(BaseModel):
    """LLM 提取的单条事实"""
    content: str = Field(..., description="第三人称短句，<=150字符")
    type: FragmentType = Field(default=FragmentType.FACT)
    entities: List[str] = Field(default_factory=list, description="涉及的实体名称")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    """LLM 提取结果"""
    facts: List[ExtractedFact] = Field(default_factory=list)


class EntityClassification(BaseModel):
    """实体分类结果"""
    entity_name: str
    entity_type: EntityType
    description: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ConsolidationResult(BaseModel):
    """碎片整合结果"""
    title: str
    content: str
    episode_type: EpisodeType = EpisodeType.INTERVIEW
    fragment_ids: List[str] = Field(default_factory=list)
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)


class SagaCluster(BaseModel):
    """传奇聚类结果"""
    title: str
    summary: str
    saga_type: SagaType = SagaType.CAREER
    entity_ids: List[str] = Field(default_factory=list)
    episode_ids: List[str] = Field(default_factory=list)
    emotion_axes: Optional[Dict[str, float]] = None


# =========================
# 检索结果模型
# =========================

class MemorySearchResult(BaseModel):
    """记忆检索结果"""
    id: str
    content: str
    source_type: str
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    importance_score: float = 0.0
    relevance_score: float = 0.0
    channel: str = "unknown"


class CognitiveProfile(BaseModel):
    """候选人认知画像"""
    user_id: str
    dimensions: Dict[str, List[CognitiveModelEntry]] = Field(default_factory=dict)
    active_states: List[CognitiveModelEntry] = Field(default_factory=list)
