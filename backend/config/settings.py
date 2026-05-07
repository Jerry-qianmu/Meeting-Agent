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
    filter_expr = os.getenv("FILTER_EXPR","")

    use_text_match_filter = os.getenv("USE_TEXT_MATCH_FILTER", "false").lower() == "true"
    keyword_filter = os.getenv("KEYWORD_FILTER","")

    ranker = os.getenv("RANKER", "RRF")
    rrf_k = int(os.getenv("RRF_K", 60))
    hybrid_alpha = float(os.getenv("HYBRID_ALPHA", 0.7))

    group_by_field = os.getenv("GROUP_BY_FIELD", "doc_id")
    group_size = int(os.getenv("GROUP_SIZE", 1))
    strict_group_size = os.getenv("STRICT_GROUP_SIZE", "false").lower() == "true"

   #""Light filter settings"
    light_filter_threshold = float(os.getenv("LIGHT_FILTER_THRESHOLD", 0.15))

    #""Rerank settings""
    rerank_model = os.getenv("RERANK_MODEL", "qwen3-vl-rerank")
    rerank_limit = int(os.getenv("RERANK_LIMIT", 20))
    rerank_final_top_k = int(os.getenv("RERANK_FINAL_TOP_K", 8))
    #---------------------------------------------------------------------------------------------------

  #""Generation settings"
    generation_model = os.getenv("GENERATION_MODEL", "deepseek-v4-pro")
    max_context_tokens = int(os.getenv("MAX_CONTEXT_TOKENS", 4096))

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

