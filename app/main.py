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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
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
    
    yield
    
    # 关闭时执行清理工作
    logger.info("清理应用资源...")
    skill_manager.cleanup_all()

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
            reload=False
        )
    except Exception as e:
        logger.error(f"REST API服务器错误: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    serve() 