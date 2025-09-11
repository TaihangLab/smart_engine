#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys
import os
import signal
import asyncio
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

# 全局应用实例引用
app_instance = None

def signal_handler(signum, frame):
    """信号处理器 - 优雅关闭应用"""
    logger.info(f"🛑 接收到信号 {signum}，开始优雅关闭...")
    
    try:
        from app.services.system_startup import system_startup_service
        
        # 在新的事件循环中运行关闭操作
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 运行关闭操作
            loop.run_until_complete(system_startup_service.shutdown_system())
            loop.close()
            
        except Exception as loop_error:
            logger.warning(f"异步关闭失败，尝试同步关闭: {str(loop_error)}")
            
            # 如果异步关闭失败，尝试直接调用关闭方法
            try:
                # 导入必要的服务并直接关闭
                from app.services.ai_task_executor import task_executor
                from app.services.llm_task_executor import llm_task_executor
                from app.services.adaptive_frame_reader import frame_reader_manager
                
                task_executor.shutdown()
                llm_task_executor.stop()
                frame_reader_manager.shutdown()
                
                logger.info("✅ 同步关闭完成")
                
            except Exception as sync_error:
                logger.error(f"同步关闭也失败: {str(sync_error)}")
            
        logger.info("✅ 应用已优雅关闭")
        
    except Exception as e:
        logger.error(f"❌ 关闭过程中出现异常: {str(e)}")
    finally:
        # 强制退出
        os._exit(0)

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # 终止信号

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