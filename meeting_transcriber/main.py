# -*- coding: utf-8 -*-
"""
会议实时转写与建议系统 - FastAPI 入口

独立启动，端口默认 8200。
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 添加项目根目录到路径
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
sys.path.insert(0, parent_dir)

from meeting_transcriber.config import meeting_config
from meeting_transcriber.api.routes import router as meeting_router
from meeting_transcriber.api.websocket import router as ws_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    logger.info("=" * 60)
    logger.info("会议转写系统启动中...")
    logger.info(f"ASR 服务: {meeting_config.asr_server_url}")
    logger.info(f"输出目录: {meeting_config.report_output_dir}")
    logger.info("=" * 60)
    yield
    logger.info("会议转写系统已关闭")


app = FastAPI(
    title="Meeting Transcriber API",
    description="会议实时转写与建议系统",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.include_router(meeting_router, prefix="/api/v1")
app.include_router(ws_router)


@app.get("/", tags=["根路径"])
async def root():
    return {
        "name": "Meeting Transcriber",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["健康检查"])
async def health_check():
    from meeting_transcriber.asr.gradio_asr import get_gradio_asr
    asr = get_gradio_asr()
    asr_ok = await asr.health_check()
    return {
        "status": "healthy" if asr_ok else "degraded",
        "asr_service": "connected" if asr_ok else "unreachable",
        "asr_url": meeting_config.asr_server_url,
    }


if __name__ == "__main__":
    if "--gui" in sys.argv:
        # 桌面弹窗模式
        from meeting_transcriber.gui import run_gui
        run_gui()
    else:
        # FastAPI 服务模式
        import uvicorn

        uvicorn.run(
            "meeting_transcriber.main:app",
            host=meeting_config.host,
            port=meeting_config.port,
            reload=meeting_config.debug,
        )
