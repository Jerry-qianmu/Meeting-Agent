# -*- coding: utf-8 -*-
"""
Memory Constellations 记忆系统

基于 MemoryConstellations 设计思想的分层自组织记忆架构
适配面试辅助 Agent 场景
"""

from .models import (
    EntityType, FragmentType, LifecycleStatus, EntityStatus,
    EpisodeType, SagaType, CorrectionType,
    MemoryFragment, MemoryEntity, MemoryEpisode, MemorySaga,
    CognitiveModelEntry, MemoryCorrection,
    ExtractedFact, ExtractionResult, EntityClassification,
    ConsolidationResult, SagaCluster,
    MemorySearchResult, CognitiveProfile,
)
from .config import MemoryConfig
