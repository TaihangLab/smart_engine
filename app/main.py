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
    """应用程序的生命周期管理"""
    # 启动时执行
    # 创建数据库表
    logger.info("创建数据库表...")
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表创建成功")
    
    # 同步Triton模型到数据库
    logger.info("正在同步Triton模型到数据库...")
    result = sync_models_from_triton()
    logger.info(f"模型同步结果: {result['message']}")
    
    # 初始化SkillManager并扫描技能
    logger.info("初始化SkillManager并扫描技能...")
    db = SessionLocal()
    try:
        # 初始化技能管理器，这会自动加载技能并同步到数据库
        skill_manager.initialize_with_db(db)
        logger.info(f"SkillManager初始化完成，已加载 {len(skill_manager.get_all_skills())} 个技能")
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
    
    yield
    
    # 关闭时执行清理工作
    logger.info("清理应用资源...")
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

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应该限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(api_router, prefix=settings.API_V1_STR)

# 添加特殊路由，确保/api/ai/monitor/alerts/{alert_id}路径可访问
from app.api.endpoints.monitor import router as monitor_router
app.include_router(monitor_router, prefix="/api/ai/monitor")

# 配置静态文件
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logger.warning(f"未能挂载静态文件目录: {str(e)}")

# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # 处理请求
    response = await call_next(request)
    
    # 记录处理时间
    process_time = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.4f}s")
    
    return response

@app.get("/")
async def root():
    """根路径，返回API信息"""
    return {
        "message": "智能分析引擎API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """健康检查接口"""
    # 检查triton服务器是否在线
    triton_status = triton_client.is_server_ready()
    
    return {
        "status": "healthy" if triton_status else "unhealthy",
        "triton_server": triton_status
    }

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