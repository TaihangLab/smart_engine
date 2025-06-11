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
from app.db.base_class import Base
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

logger = logging.getLogger(__name__)

# 创建FastAPI应用
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 Smart Engine 应用启动中...")
    
    # 启动时执行初始化工作
    logger.info("开始数据库初始化...")
    
    # 创建数据库表
    logger.info("创建数据库表...")
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表创建成功")
    
    # 同步Triton模型到数据库（如果Triton可用）
    logger.info("正在同步Triton模型到数据库...")
    try:
        result = sync_models_from_triton()
        logger.info(f"模型同步结果: {result['message']}")
    except Exception as e:
        logger.warning(f"模型同步失败（Triton可能未启动）: {str(e)}")
        logger.info("Triton客户端已配置自动重连，首次调用时会自动连接")
    
    # 初始化数据库连接并设置SkillManager
    db = SessionLocal()
    try:
        # 初始化技能管理器，这会自动加载技能并同步到数据库
        skill_manager.initialize_with_db(db)
        available_skills = skill_manager.get_available_skill_classes()
        logger.info(f"SkillManager初始化完成，已加载 {len(available_skills)} 个技能类")
    except Exception as e:
        logger.error(f"初始化SkillManager失败: {str(e)}", exc_info=True)
    finally:
        db.close()
    
    # 初始化RabbitMQ和报警服务（这些服务在导入时已自动初始化）
    logger.info("RabbitMQ和报警服务已初始化")
    
    # 初始化AI任务执行器并为所有任务创建调度计划
    logger.info("初始化AI任务执行器...")
    try:
        task_executor.schedule_all_tasks()
        logger.info("已为所有AI任务创建调度计划")
    except Exception as e:
        logger.error(f"初始化AI任务执行器失败: {str(e)}", exc_info=True)
    
    # 🚀 架构优化：移除sse_publisher后台任务
    # 原因：优化后架构采用直接异步广播机制，不再需要中间队列处理任务
    # logger.info("启动SSE发布者任务...")
    # asyncio.create_task(sse_publisher())
    # logger.info("SSE发布者任务已启动")
    logger.info("✅ 优化后的报警服务已采用直接广播架构，无需启动额外的后台任务")
    
    # 🔄 启动报警补偿服务
    logger.info("启动报警补偿服务...")
    try:
        from app.services.alert_compensation_service import start_compensation_service
        asyncio.create_task(start_compensation_service())
        logger.info("✅ 报警补偿服务已启动")
    except Exception as e:
        logger.error(f"❌ 启动报警补偿服务失败: {str(e)}")
    
    # 🔗 启动SSE连接管理器
    logger.info("启动SSE连接管理器...")
    try:
        await sse_manager.start()
        logger.info("✅ SSE连接管理器已启动")
    except Exception as e:
        logger.error(f"❌ 启动SSE连接管理器失败: {str(e)}")
    
    # ✅ 系统架构已完全简化，无需恢复机制
    
    logger.info("✅ Smart Engine 应用启动完成")
    
    yield
    
    # 关闭时执行清理工作
    logger.info("🛑 Smart Engine 应用关闭中...")
    
    try:
        # 关闭补偿服务
        from app.services.alert_compensation_service import stop_compensation_service
        stop_compensation_service()
        logger.info("✅ 报警补偿服务已关闭")
        
        # 关闭SSE连接管理器
        try:
            await sse_manager.stop()
            logger.info("✅ SSE连接管理器已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭SSE连接管理器失败: {str(e)}")
        
        # 系统正常关闭
        logger.info("📝 系统正常关闭")
        
        logger.info("✅ Smart Engine 应用关闭完成")
        
    except Exception as e:
        logger.error(f"❌ 应用关闭过程中发生错误: {str(e)}", exc_info=True)
    
    skill_manager.cleanup_all()
    
    # 关闭RabbitMQ连接
    from app.services.rabbitmq_client import rabbitmq_client
    rabbitmq_client.close()
    
    # 关闭任务执行器的调度器
    try:
        task_executor.scheduler.shutdown()
        logger.info("AI任务执行器调度器已关闭")
    except Exception as e:
        logger.error(f"关闭AI任务执行器调度器失败: {str(e)}")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.PROJECT_VERSION,
    lifespan=lifespan
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