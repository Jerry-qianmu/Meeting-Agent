# -*- coding: utf-8 -*-
"""
Memory Constellations 记忆系统配置

所有模型名称和 API Key 统一在此管理，支持环境变量覆盖。
"""

import os


class MemoryConfig:
    """记忆系统全局配置"""

    # ====================
    # API Key
    # ====================
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    # ====================
    # 模型配置（支持环境变量覆盖）
    # ====================
    MEMORY_LLM_MODEL = os.getenv("MEMORY_LLM_MODEL", "qwen3.6-max-preview")
    MEMORY_DEEP_LLM_MODEL = os.getenv("MEMORY_DEEP_LLM_MODEL", "qwen3.6-max-preview")
    MEMORY_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
    MEMORY_EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

    # ====================
    # Scribe
    # ====================
    SCRIBE_TRIGGER_SILENCE_MINUTES = 20
    SCRIBE_BACKLOG_THRESHOLD = 50
    SCRIBE_MAX_FRAGMENT_LENGTH = 150
    SCRIBE_EXTRACTION_BATCH_SIZE = 20

    # ====================
    # Archivist
    # ====================
    ARCHIVIST_TICK_INTERVAL_SECONDS = 120
    ARCHIVIST_DEEP_CYCLE_IDLE_MINUTES = 60

    # ====================
    # Librarian
    # ====================
    LIBRARIAN_EPISODE_BOOST = 1.5
    LIBRARIAN_VECTOR_FLOOR = 0.3
    LIBRARIAN_TOP_K = 10
    LIBRARIAN_RRF_K = 60

    # ====================
    # Lifecycle
    # ====================
    FRAGMENT_ACTIVE_TO_COOLING_DAYS = 14
    FRAGMENT_COOLING_TO_FROZEN_DAYS = 30
    FRAGMENT_FROZEN_TO_TOMBSTONE_DAYS = 90
    EPISODE_ACTIVE_TO_MATURE_MONTHS = 6
    EPISODE_MATURE_TO_ARCHIVED_MONTHS = 12

    # ====================
    # Entity
    # ====================
    ENTITY_SEED_GRADUATE_THRESHOLD = 3
    ENTITY_MERGE_SIMILARITY_THRESHOLD = 0.8

    # ====================
    # CognitiveModel
    # ====================
    COGNITIVE_MODEL_DEFAULT_TTL_DAYS = 90
    COGNITIVE_MODEL_MAX_STATES = 50

    # ====================
    # Milvus
    # ====================
    MEMORY_FRAGMENTS_COLLECTION = "memory_fragments_{user_id}"
    MEMORY_EPISODES_COLLECTION = "memory_episodes_{user_id}"
