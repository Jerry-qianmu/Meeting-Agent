import os
from dotenv import load_dotenv

load_dotenv()

class Settings:

    def __init__(self):
        pass

    #"""Mysql settings"""
    mysql_host = os.getenv("MYSQL_HOST","localhost")
    mysql_user = os.getenv("MYSQL_USER","root")
    mysql_password = os.getenv("MYSQL_PASSWORD")
    mysql_db = os.getenv("MYSQL_DB")
    mysql_port = os.getenv("MYSQL_PORT",3306)

    #"""Milvus settings""""
    milvus_host = os.getenv("MILVUS_HOST","localhost")
    milvus_port = os.getenv("MILVUS_PORT",19530)
    milvus_user = os.getenv("MILVUS_USER")
    milvus_password = os.getenv("MILVUS_PASSWORD")
    milvus_url = os.getenv("MILVUS_URL")

   #"""Embedding settings"""
    embedding_model = os.getenv("EMBEDDING_MODEL","text-embedding-v4")
    embedding_dimension = int(os.getenv("EMBEDDING_DIMENSION",1536))
    embedding_batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE",32))


    #"""Dashscoope settings"""
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    dashscope_base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    #""LLM 统一配置（全局默认）""
    llm_api_type = os.getenv("LLM_API_TYPE", "dashscope")       # dashscope / openai
    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    llm_base_url = os.getenv("LLM_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    #""LLM 各用途独立配置（可单独覆盖 api_type / model / api_key / base_url）""
    # 不设置的字段 fallback 到全局默认

    # Query Rewrite
    rewrite_api_type = os.getenv("REWRITE_API_TYPE", "")        # 空=用全局默认
    rewrite_api_key = os.getenv("REWRITE_API_KEY", "")
    rewrite_base_url = os.getenv("REWRITE_BASE_URL", "")

    # Answer Generation
    generation_api_type = os.getenv("GENERATION_API_TYPE", "")
    generation_api_key = os.getenv("GENERATION_API_KEY", "")
    generation_base_url = os.getenv("GENERATION_BASE_URL", "")

    # Quality Evaluation
    quality_eval_api_type = os.getenv("QUALITY_EVAL_API_TYPE", "")
    quality_eval_api_key = os.getenv("QUALITY_EVAL_API_KEY", "")
    quality_eval_base_url = os.getenv("QUALITY_EVAL_BASE_URL", "")

    # Memory Compression
    memory_compress_api_type = os.getenv("MEMORY_COMPRESS_API_TYPE", "")
    memory_compress_api_key = os.getenv("MEMORY_COMPRESS_API_KEY", "")
    memory_compress_base_url = os.getenv("MEMORY_COMPRESS_BASE_URL", "")

    # Chunk Enrichment
    md_enrich_api_type = os.getenv("MD_ENRICH_API_TYPE", "")
    md_enrich_api_key = os.getenv("MD_ENRICH_API_KEY", "")
    md_enrich_base_url = os.getenv("MD_ENRICH_BASE_URL", "")

    # Memory（scribe / entity_resolver / archivist / consolidator / cognitive）
    memory_api_type = os.getenv("MEMORY_API_TYPE", "")
    memory_api_key = os.getenv("MEMORY_API_KEY", "")
    memory_base_url = os.getenv("MEMORY_BASE_URL", "")

  #""""query_write settings""""
    max_history_turns = int(os.getenv("MAX_HISTORY_TURNS",3))

    #""""Short-term Memory settings""""
    memory_token_threshold = int(os.getenv("MEMORY_TOKEN_THRESHOLD", 2000))   # 触发压缩的 token 阈值
    memory_buffer_rounds = int(os.getenv("MEMORY_BUFFER_ROUNDS", 3))          # 缓冲区保留的最近轮数
    memory_compress_model = os.getenv("MEMORY_COMPRESS_MODEL", "deepseek-v4-pro")  # 压缩用模型

    #"""query_expansion settings"""
    # max_expansions = int(os.getenv("MAX_EXPANSIONS",5))

   #""RAG config"""------------------------------------------------------------------------------------
    rewrite_model = os.getenv("REWRITE_MODEL","deepseek-v4-pro")
    determine_retrieval_strategy_model = os.getenv("DETERMINE_RETRIEVAL_STRATEGY_MODEL","deepseek-v4-pro")

    collection_name = os.getenv("COLLECTION_NAME","")
    top_k = int(os.getenv("TOP_K",10))
    search_limit = int(os.getenv("SEARCH_LIMIT", 50))  # Milvus 内部搜索候选池大小，需 >= top_k
    filter_expr = os.getenv("FILTER_EXPR","")

    use_text_match_filter = os.getenv("USE_TEXT_MATCH_FILTER", "false").lower() == "true"
    keyword_filter = os.getenv("KEYWORD_FILTER","")

    ranker = os.getenv("RANKER", "RRF")
    rrf_k = int(os.getenv("RRF_K", 60))
    hybrid_alpha = float(os.getenv("HYBRID_ALPHA", 0.7))

    group_by_field = os.getenv("GROUP_BY_FIELD", "")  # 默认不分组，避免同文档多 chunk 被过滤
    group_size = int(os.getenv("GROUP_SIZE", 5))
    strict_group_size = os.getenv("STRICT_GROUP_SIZE", "false").lower() == "true"

   #""Light filter settings"
    light_filter_threshold = float(os.getenv("LIGHT_FILTER_THRESHOLD", 0.05))

    #""Rerank settings""
    rerank_model = os.getenv("RERANK_MODEL", "qwen3-rerank")
    rerank_limit = int(os.getenv("RERANK_LIMIT", 40))
    rerank_final_top_k = int(os.getenv("RERANK_FINAL_TOP_K", 20))

    #""Markdown Chunking settings""
    md_chunk_min_tokens = int(os.getenv("MD_CHUNK_MIN_TOKENS", 200))
    md_chunk_max_tokens = int(os.getenv("MD_CHUNK_MAX_TOKENS", 800))
    md_chunk_target_tokens = int(os.getenv("MD_CHUNK_TARGET_TOKENS", 500))
    md_chunk_prepend_heading = os.getenv("MD_CHUNK_PREPEND_HEADING", "true").lower() == "true"
    md_chunk_overlap_ratio = float(os.getenv("MD_CHUNK_OVERLAP_RATIO", "0.15"))

    # ── Chunk Merge settings ──────────────────────────────────────────────────────
    chunk_merge_enable = os.getenv("CHUNK_MERGE_ENABLE", "true").lower() == "true"
    chunk_merge_max_tokens = int(os.getenv("CHUNK_MERGE_MAX_TOKENS", 1000))
    chunk_merge_max_gap = int(os.getenv("CHUNK_MERGE_MAX_GAP", 2))
    chunk_merge_enable_context_expansion = os.getenv("CHUNK_MERGE_ENABLE_CONTEXT_EXPANSION", "true").lower() == "true"
    chunk_merge_min_tokens_for_expansion = int(os.getenv("CHUNK_MERGE_MIN_TOKENS_FOR_EXPANSION", 200))
    chunk_merge_enable_second_rerank = os.getenv("CHUNK_MERGE_ENABLE_SECOND_RERANK", "true").lower() == "true"
    chunk_merge_second_rerank_limit = int(os.getenv("CHUNK_MERGE_SECOND_RERANK_LIMIT", 30))
    chunk_merge_final_top_k = int(os.getenv("CHUNK_MERGE_FINAL_TOP_K", 20))
    #---------------------------------------------------------------------------------------------------

  #""Generation settings"
    generation_model = os.getenv("GENERATION_MODEL", "deepseek-v4-pro")
    max_context_tokens = int(os.getenv("MAX_CONTEXT_TOKENS", 8192))

    #""Quality Control settings""
    quality_eval_model = os.getenv("QUALITY_EVAL_MODEL","deepseek-v4-pro")
    quality_max_retries = int(os.getenv("QUALITY_MAX_RETRIES",2))
    
    # 质量通过阈值
    quality_score_threshold = float(os.getenv("QUALITY_SCORE_THRESHOLD",0.6))
    quality_groundedness_threshold = float(os.getenv("QUALITY_GROUNDEDNESS_THRESHOLD",0.5))
    quality_relevance_threshold = float(os.getenv("QUALITY_RELEVANCE_THRESHOLD",0.5))
    
    # 重试策略参数
    retry_broaden_threshold_delta = float(os.getenv("RETRY_BROADEN_THRESHOLD_DELTA",-0.05))
    retry_broaden_topk_delta = int(os.getenv("RETRY_BROADEN_TOPK_DELTA",5))
    retry_narrow_threshold_delta = float(os.getenv("RETRY_NARROW_THRESHOLD_DELTA",0.1))
    retry_narrow_topk_delta = int(os.getenv("RETRY_NARROW_TOPK_DELTA",-3))
    retry_increase_topk_delta = int(os.getenv("RETRY_INCREASE_TOPK_DELTA",5))

   #"OSS settings"
    oss_access_key_id = os.getenv("OSS_ACCESS_KEY_ID")
    oss_access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
    oss_region = os.getenv("OSS_REGION","cn-hangzhou")
    oss_endpoint = os.getenv("OSS_ENDPOINT","oss-cn-hangzhou.aliyuncs.com")
    oss_bucket = os.getenv("OSS_BUCKET","my-knowledge-agent")
    oss_prefix = os.getenv("OSS_PREFIX","")  # OSS 路径前缀（可选）
    
    # FastAPI settings
    host = os.getenv("FASTAPI_HOST","0.0.0.0")
    port = int(os.getenv("FASTAPI_PORT",8000))
    debug = os.getenv("FASTAPI_DEBUG","false").lower() == "true"
    
    # CORS settings
    cors_origins = os.getenv("CORS_ORIGINS","*").split(",")

    # ── MCP Settings ─────────────────────────────────────────────────────
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    mcp_tool_call_timeout: int = int(os.getenv("MCP_TOOL_CALL_TIMEOUT", "30"))
    mcp_server_startup_timeout: int = int(os.getenv("MCP_SERVER_STARTUP_TIMEOUT", "15"))
    mcp_max_tool_calls: int = int(os.getenv("MCP_MAX_TOOL_CALLS", "5"))

    def get_llm_config(self, use_case: str, model: str = None) -> dict:
        """
        获取指定用途的 LLM 配置，未设置的字段 fallback 到全局默认

        Args:
            use_case: rewrite / generation / quality_eval / memory_compress / md_enrich / memory
            model: 覆盖模型名（用于 memory 子系统各自指定模型）

        Returns:
            {"api_type": str, "api_key": str, "base_url": str, "model": str}
        """
        api_type = getattr(self, f"{use_case}_api_type", "") or self.llm_api_type
        api_key = getattr(self, f"{use_case}_api_key", "") or self.llm_api_key
        base_url = getattr(self, f"{use_case}_base_url", "") or self.llm_base_url
        if not model:
            model = getattr(self, f"{use_case}_model", "") or self.generation_model
        return {"api_type": api_type, "api_key": api_key, "base_url": base_url, "model": model}

