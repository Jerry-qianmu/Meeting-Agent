# -*- coding: utf-8 -*-
"""
FastAPI 应用入口
提供知识库和文档管理的 REST API
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

import os
import sys

# 添加项目根目录到路径
cur_dir = os.path.dirname(__file__)
sys.path.insert(0, cur_dir)

from config.settings import Settings
from database.mysql.mysql_client import init_mysql_pool, close_mysql_pool, get_db_client
from database.mysql.init_database import DatabaseInitializer

# 加载配置
settings = Settings()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def initialize_database():
    """
    初始化数据库表结构（同步函数）
    
    检查并创建所有必要的表，幂等操作
    """
    db_client = get_db_client()
    
    try:
        initializer = DatabaseInitializer(db_client)
        success = initializer.initialize_database(drop_existing=False)
        
        if success:
            # 验证表
            verification = initializer.verify_tables()
            created_count = sum(1 for exists in verification.values() if exists)
            logger.info(f"数据库表初始化完成，共 {created_count} 个表")
        else:
            logger.warning("数据库表初始化失败")
            
    except Exception as e:
        logger.error(f"数据库表初始化失败：{e}")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    应用生命周期管理
    
    启动时：
    1. 初始化数据库连接池
    2. 检查并初始化数据库表结构
    3. 初始化 Milvus 连接
    
    关闭时：
    1. 关闭数据库连接池
    """
    # ── 启动 ────────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("应用启动中...")
    logger.info("=" * 60)
    
    try:
        # 1. 初始化 MySQL 连接池
        init_mysql_pool(settings)
        
        # 2. 检查连接
        db_client = get_db_client()
        if db_client.check_connection():
            logger.info("MySQL 连接检查通过")
        else:
            logger.warning("MySQL 连接检查失败")
        
        # 3. 检查并初始化数据库表（幂等）
        # 使用 asyncio.to_thread 在后台线程执行同步的初始化操作
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, initialize_database)
        
        # 4. 测试 Milvus 连接（MilvusService 会在首次使用时自动初始化）
        from database.milvus.milvus_service import MilvusService
        milvus_service = MilvusService()
        collections = milvus_service.list_collections()
        logger.info(f"Milvus 连接成功，现有 collections: {collections if collections else '空'}")
        
        # 5. 测试 OSS 连接
        from database.oss.oss_service import get_oss_service
        oss_service = get_oss_service()
        logger.info(f"OSS 连接成功，bucket: {oss_service.bucket}")
        
        logger.info("=" * 60)
        logger.info("应用启动完成")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ 应用启动失败：{e}")
        raise
    
    yield
    
    # ── 关闭 ────────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("应用关闭中...")
    logger.info("=" * 60)
    
    try:
        # 关闭 MySQL 连接池
        close_mysql_pool()
        
    except Exception as e:
        logger.error(f"应用关闭时出错：{e}")
    
    logger.info("应用已关闭")


# ── 创建 FastAPI 应用 ───────────────────────────────────────────────────────

app = FastAPI(
    title="Knowledge Base API",
    description="知识库和文档管理系统 API\n\n"
                "## 功能特性\n\n"
                "- **知识库管理**: 创建、查询、更新、删除知识库\n"
                "- **文档上传**: 支持 PDF、TXT、MD 格式\n"
                "- **自动处理**: PDF 解析、文档分块、向量化\n"
                "- **向量检索**: 基于 Milvus 的混合检索\n",
    version="1.0.0",
    lifespan=lifespan
)

# ── CORS 中间件 ────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 路由注册 ──────────────────────────────────────────────────────────────

from api_controller import knowledge_base_router, document_router, agent_router,  session_router, auth_router

app.include_router(auth_router, prefix="/api/v1")
app.include_router(knowledge_base_router, prefix="/api/v1")
app.include_router(document_router, prefix="/api/v1")
app.include_router(agent_router, prefix="/api/v1")

app.include_router(session_router, prefix="/api/v1")


# ── 健康检查 ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["健康检查"])
async def health_check():
    """健康检查接口"""
    try:
        db_client = get_db_client()
        mysql_status = "connected" if db_client.check_connection() else "unhealthy"
    except Exception as e:
        mysql_status = f"error: {str(e)}"
    
    return {
        "status": "healthy" if mysql_status == "connected" else "unhealthy",
        "mysql": mysql_status,
        "timestamp": asyncio.get_event_loop().time()
    }


@app.get("/", tags=["根路径"])
async def root():
    """根路径"""
    return {
        "message": "Knowledge Base API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


# ── 异常处理 ──────────────────────────────────────────────────────────────

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request, exc):
    """处理 SQLAlchemy 数据库异常"""
    logger.error(f"数据库错误：{exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "数据库操作失败", "error": str(exc)}
    )


# ── 主函数 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    
    host = getattr(settings, 'host', '0.0.0.0')
    port = getattr(settings, 'port', 8000)
    debug = getattr(settings, 'debug', False)
    
    logger.info(f"启动 Uvicorn: {host}:{port}, debug={debug}")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug
    )
