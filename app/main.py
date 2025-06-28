#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import time
import sys
import os
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app.services.model_service import sync_models_from_triton
from app.core.config import settings
from app.db.session import get_db, engine, SessionLocal
from app.db.base import Base
from app.api import api_router
from app.services.triton_client import triton_client
from app.skills.skill_manager import skill_manager
from app.services.ai_task_executor import task_executor

# 导入报警服务相关内容
import app.services.rabbitmq_client
import app.services.alert_service
from app.services.sse_connection_manager import sse_manager

# 导入中间件和系统级路由
from app.core.middleware import RequestLoggingMiddleware

# 🔥 优化后架构不再需要sse_publisher后台任务
# from app.services.alert_service import sse_publisher

# 配置日志
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(settings.BASE_DIR, 'app.log'))
    ]
)

# 设置特定模块的日志级别
logging.getLogger('app.services.rabbitmq_client').setLevel(log_level)
logging.getLogger('app.services.alert_service').setLevel(log_level)
logging.getLogger('app.api.endpoints.alerts').setLevel(log_level)
logging.getLogger('app.skills.skill_base').setLevel(log_level)
logging.getLogger('app.plugins.skills').setLevel(log_level)
logging.getLogger('app.services.adaptive_frame_reader').setLevel(log_level)

logger = logging.getLogger(__name__)

# 🚀 导入零配置企业级启动服务
from app.services.system_startup import lifespan as startup_lifespan

# 创建FastAPI应用 - 集成零配置补偿架构
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.PROJECT_VERSION,
    lifespan=startup_lifespan  # 使用零配置启动服务
)



# 配置中间件
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应该限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 注册API路由
app.include_router(api_router, prefix=settings.API_V1_STR)



# 配置静态文件
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logger.warning(f"未能挂载静态文件目录: {str(e)}")

# ✅ 系统采用简化架构，无需重启恢复机制

def serve():
    """启动REST API服务"""
    try:
        logger.info(f"启动REST API服务，端口 {settings.REST_PORT}...")
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=settings.REST_PORT,
            reload=False,
            log_level=settings.LOG_LEVEL.lower()
        )
    except Exception as e:
        logger.error(f"REST API服务器错误: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    serve() 