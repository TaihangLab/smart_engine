#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app.core.config import settings
from app.api import api_router

# 导入中间件
from app.core.middleware import RequestLoggingMiddleware

# 🚀 导入零配置企业级启动服务
from app.services.system_startup import lifespan as startup_lifespan

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


def serve():
    """启动REST API服务"""
    try:
        logger.info(f"🚀 启动Smart Engine REST API服务，端口 {settings.REST_PORT}...")
        logger.info("✨ 采用零配置企业级架构，所有服务将自动启动")
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=settings.REST_PORT,
            reload=False,
            log_level=settings.LOG_LEVEL.lower()
        )
    except Exception as e:
        logger.error(f"❌ REST API服务器错误: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    serve() 